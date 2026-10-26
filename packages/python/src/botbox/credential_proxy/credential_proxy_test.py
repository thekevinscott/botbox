import asyncio
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from botbox.credential_proxy import credential_proxy as module
from botbox.credential_proxy.credential_proxy import credential_proxy
from botbox.credential_proxy.envoy_config import IMAGE, SECRET_FILE, Injection

INJECTION = Injection("api.anthropic.com", "/v1/messages", "Authorization")


class Client:
    """The attached `docker run`: serves the socket unless told to exit, until cancelled."""

    def __init__(self, steps: list[str]) -> None:
        self.steps = steps
        self.args: list[str] = []
        self.stdin = b""
        self.stdin_fd = -1
        self.exits: int | None = None
        self.serves = True
        self.ignores_stop = False
        self.stopped: asyncio.Event | None = None

    async def __call__(self, args: list[str], **options: Any) -> int:
        self.args, self.stdin_fd = args, options["stdin"]
        self.stdin = os.read(options["stdin"], 1 << 16)
        options["stdout"].write(b"envoy said this\n")
        options["stdout"].flush()
        if self.exits is not None:
            return self.exits
        server = None
        if self.serves:
            socket = Path(args[args.index("--volume") + 1].split(":")[0]) / "credentials.sock"
            server = await asyncio.start_unix_server(lambda _, w: w.close(), socket)
        self.stopped = asyncio.Event()
        try:
            await (asyncio.Event() if self.ignores_stop else self.stopped).wait()
            return 137
        except asyncio.CancelledError:
            self.steps.append("client cancelled")
            raise
        finally:
            if server is not None:
                server.close()

    def stop(self, *args: str) -> None:
        self.steps.append(" ".join(args))
        if self.stopped is not None:
            self.stopped.set()


@pytest.fixture
def steps() -> list[str]:
    return []


@pytest.fixture(autouse=True)
def client(steps: list[str]) -> Iterator[Client]:
    fake = Client(steps)
    with patch(f"{__package__}.credential_proxy.run", fake):
        yield fake


@pytest.fixture(autouse=True)
def run_docker(client: Client) -> Iterator[AsyncMock]:
    with patch(f"{__package__}.credential_proxy.run_docker", side_effect=client.stop) as m:
        yield m


@pytest.fixture(autouse=True)
def remove(steps: list[str]) -> Iterator[AsyncMock]:
    with patch(
        f"{__package__}.credential_proxy.remove", side_effect=lambda n: steps.append(f"rm {n}")
    ) as m:
        yield m


@pytest.fixture
def sockets(tmp_path: Path) -> Path:
    path = tmp_path / "sockets"
    path.mkdir()
    return path


def start(sockets: Path, secret: str = "Bearer one") -> Any:
    return credential_proxy(
        INJECTION,
        secret,
        proxy="botbox-proxy-t",
        sockets=sockets,
        token="t",
        log=sockets.parent / "envoy.log",
    )


def flag(args: list[str], name: str) -> list[str]:
    return [args[i + 1] for i, arg in enumerate(args) if arg == name]


def describe_credential_proxy() -> None:
    async def it_yields_the_container_and_its_socket(sockets: Path) -> None:
        async with start(sockets) as proxy:
            assert proxy.name == "botbox-credentials-t"
            assert proxy.socket == sockets / "credentials.sock"

    async def it_feeds_the_first_secret_on_stdin(sockets: Path, client: Client) -> None:
        async with start(sockets, "Bearer one"):
            (resource,) = json.loads(client.stdin)["resources"]
            assert resource["generic_secret"]["secret"]["inline_string"] == "Bearer one"

    async def it_locks_the_container_down_in_the_proxys_pid_namespace(
        sockets: Path, client: Client
    ) -> None:
        async with start(sockets):
            args = client.args
        assert flag(args, "--name") == ["botbox-credentials-t"]
        assert flag(args, "--label") == ["botbox.run=t"]
        assert flag(args, "--user") == ["101:101"]
        assert flag(args, "--pid") == ["container:botbox-proxy-t"]
        assert flag(args, "--network") == ["bridge"]
        assert flag(args, "--cap-drop") == ["ALL"]
        assert flag(args, "--security-opt") == ["no-new-privileges"]
        assert flag(args, "--log-driver") == ["none"]
        assert flag(args, "--pids-limit") == ["64"]
        assert flag(args, "--tmpfs") == ["/run/credentials:uid=101,gid=101,mode=0700"]
        assert flag(args, "--volume") == [f"{sockets}:/run/botbox:rw"]
        assert "--interactive" in args
        assert flag(args, "--entrypoint") == ["sh"]

    async def it_writes_the_secret_then_execs_envoy_on_the_config(
        sockets: Path, client: Client
    ) -> None:
        async with start(sockets):
            args = client.args
        image = args.index(IMAGE)
        script, secret_file, config = args[image + 2], args[image + 4], args[image + 5]
        assert args[image + 1 : image + 4 : 2] == ["-c", "sh"]
        assert script.startswith('cat >"$1" && exec envoy ')
        assert script.endswith('--config-yaml "$2"')
        assert secret_file == SECRET_FILE
        listener = json.loads(config)["static_resources"]["listeners"][0]
        assert listener["address"]["pipe"]["path"] == "/run/botbox/credentials.sock"
        assert len(args) == image + 6

    async def it_logs_envoys_output_to_the_file(sockets: Path) -> None:
        async with start(sockets):
            pass
        assert (sockets.parent / "envoy.log").read_bytes() == b"envoy said this\n"

    async def it_stops_the_container_then_removes_it(sockets: Path, steps: list[str]) -> None:
        async with start(sockets):
            assert steps == []
        assert steps == ["stop --time 5 botbox-credentials-t", "rm botbox-credentials-t"]

    async def it_kills_a_client_that_outlives_the_stop(
        sockets: Path, client: Client, steps: list[str]
    ) -> None:
        client.ignores_stop = True
        with patch.object(module, "STOP_SECONDS", 0.01):
            async with start(sockets):
                pass
        assert steps == [
            "stop --time 0.01 botbox-credentials-t",
            "client cancelled",
            "rm botbox-credentials-t",
        ]

    async def it_removes_it_when_the_block_raises(sockets: Path, steps: list[str]) -> None:
        with pytest.raises(ValueError):
            async with start(sockets):
                raise ValueError
        assert steps[-1] == "rm botbox-credentials-t"

    async def it_closes_the_stdin_pipe(sockets: Path, client: Client) -> None:
        async with start(sockets):
            os.fstat(client.stdin_fd)
        with pytest.raises(OSError):
            os.fstat(client.stdin_fd)

    async def it_warns_when_it_cannot_remove_the_container(
        sockets: Path, remove: AsyncMock
    ) -> None:
        remove.side_effect = RuntimeError("daemon gone")
        with pytest.warns(
            RuntimeWarning, match="credential proxy botbox-credentials-t: daemon gone"
        ):
            async with start(sockets):
                pass

    async def it_raises_with_the_log_if_envoy_exits_first(sockets: Path, client: Client) -> None:
        client.exits = 1
        with pytest.raises(RuntimeError, match="did not start:\nenvoy said this"):
            async with start(sockets):
                pytest.fail("yielded")

    async def it_gives_up_waiting_for_the_socket(
        sockets: Path, client: Client, steps: list[str]
    ) -> None:
        client.serves = False
        with (
            patch.object(module, "READY_SECONDS", 0.1),
            pytest.raises(RuntimeError, match="did not start"),
        ):
            async with start(sockets):
                pytest.fail("yielded")
        assert steps[-1] == "rm botbox-credentials-t"

    async def it_waits_for_the_socket_to_accept_rather_than_to_exist(
        sockets: Path, client: Client
    ) -> None:
        client.serves = False
        (sockets / "credentials.sock").touch()
        with patch.object(module, "READY_SECONDS", 0.1), pytest.raises(RuntimeError):
            async with start(sockets):
                pytest.fail("yielded")
