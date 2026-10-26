import asyncio
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from botbox.credential_proxy.credential_proxy import credential_proxy

MODULE = f"{__package__}.credential_proxy"
INJECTION = object()


class Client:
    """The attached `docker run`, running until cancelled unless told to exit."""

    def __init__(self) -> None:
        self.args: list[str] = []
        self.stdin: int = -1
        self.exits: int | None = None

    async def __call__(self, args: list[str], **options: Any) -> int:
        self.args, self.stdin = args, options["stdin"]
        options["stdout"].write(b"envoy said this\n")
        options["stdout"].flush()
        if self.exits is not None:
            return self.exits
        await asyncio.Event().wait()
        return 0


@pytest.fixture
def steps() -> list[str]:
    return []


@pytest.fixture(autouse=True)
def client() -> Iterator[Client]:
    fake = Client()
    with patch(f"{MODULE}.run", fake):
        yield fake


@pytest.fixture(autouse=True)
def envoy_config() -> Iterator[Mock]:
    with patch(f"{MODULE}.envoy_config", return_value="the-config") as m:
        yield m


@pytest.fixture(autouse=True)
def sds_secret() -> Iterator[Mock]:
    with patch(f"{MODULE}.sds_secret", return_value=b"the-sds") as m:
        yield m


@pytest.fixture(autouse=True)
def preloaded() -> Iterator[Mock]:
    with patch(f"{MODULE}.preloaded", side_effect=lambda _: os.open(os.devnull, os.O_RDONLY)) as m:
        yield m


@pytest.fixture(autouse=True)
def constants() -> Iterator[None]:
    with (
        patch(f"{MODULE}.IMAGE", "envoy-image"),
        patch(f"{MODULE}.SECRET_DIR", "/secrets"),
        patch(f"{MODULE}.SECRET_FILE", "/secrets/s.json"),
    ):
        yield


@pytest.fixture(autouse=True)
def wait_for_socket(steps: list[str]) -> Iterator[AsyncMock]:
    async def ready(*_: object) -> None:
        await asyncio.sleep(0)
        steps.append("ready")

    with patch(f"{MODULE}.wait_for_socket", side_effect=ready) as m:
        yield m


@pytest.fixture(autouse=True)
def stop_container(steps: list[str]) -> Iterator[AsyncMock]:
    async def stop(client: asyncio.Future[int], name: str) -> None:
        client.cancel()
        steps.append(f"stop {name}")

    with patch(f"{MODULE}.stop_container", side_effect=stop) as m:
        yield m


@pytest.fixture
def sockets(tmp_path: Path) -> Path:
    return tmp_path / "sockets"


@pytest.fixture
def log(tmp_path: Path) -> Path:
    return tmp_path / "envoy.log"


def start(sockets: Path, log: Path) -> Any:
    return credential_proxy(
        INJECTION,  # type: ignore[arg-type]
        "Bearer one",
        proxy="botbox-proxy-t",
        sockets=sockets,
        token="t",
        log=log,
    )


def flag(args: list[str], name: str) -> list[str]:
    return [args[i + 1] for i, arg in enumerate(args) if arg == name]


def describe_credential_proxy() -> None:
    async def it_yields_the_container_and_its_socket(sockets: Path, log: Path) -> None:
        async with start(sockets, log) as proxy:
            assert proxy.name == "botbox-credentials-t"
            assert proxy.socket == sockets / "credentials.sock"

    async def it_feeds_the_first_secret_on_stdin(
        sockets: Path, log: Path, sds_secret: Mock, preloaded: Mock
    ) -> None:
        async with start(sockets, log):
            sds_secret.assert_called_once_with("Bearer one")
            preloaded.assert_called_once_with(b"the-sds")

    async def it_serves_the_injection_on_the_mounted_socket(
        sockets: Path, log: Path, envoy_config: Mock
    ) -> None:
        async with start(sockets, log):
            envoy_config.assert_called_once_with(INJECTION, "/run/botbox/credentials.sock")

    async def it_locks_the_container_down_in_the_proxys_pid_namespace(
        sockets: Path, log: Path, client: Client
    ) -> None:
        async with start(sockets, log):
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
        assert flag(args, "--tmpfs") == ["/secrets:uid=101,gid=101,mode=0700"]
        assert flag(args, "--volume") == [f"{sockets}:/run/botbox:rw"]
        assert flag(args, "--entrypoint") == ["sh"]
        assert args[0] == "--interactive"

    async def it_writes_the_secret_then_execs_envoy_on_the_config(
        sockets: Path, log: Path, client: Client
    ) -> None:
        async with start(sockets, log):
            args = client.args
        image = args.index("envoy-image")
        assert args[image:] == [
            "envoy-image",
            "-c",
            args[image + 2],
            "sh",
            "/secrets/s.json",
            "the-config",
        ]
        assert args[image + 2].startswith('cat >"$1" && exec envoy ')
        assert args[image + 2].endswith(' --config-yaml "$2"')

    async def it_logs_envoys_output_to_the_file(sockets: Path, log: Path) -> None:
        async with start(sockets, log):
            pass
        assert log.read_bytes() == b"envoy said this\n"

    async def it_waits_for_the_socket_before_yielding(
        sockets: Path, log: Path, steps: list[str], wait_for_socket: AsyncMock
    ) -> None:
        async with start(sockets, log):
            steps.append("yielded")
        (socket, client, waited_log, timeout), _ = wait_for_socket.call_args
        assert (socket, waited_log, timeout) == (sockets / "credentials.sock", log, 30)
        assert isinstance(client, asyncio.Future)
        assert steps == ["ready", "yielded", "stop botbox-credentials-t"]

    async def it_stops_the_container_when_the_block_raises(
        sockets: Path, log: Path, steps: list[str]
    ) -> None:
        with pytest.raises(ValueError):
            async with start(sockets, log):
                raise ValueError
        assert steps[-1] == "stop botbox-credentials-t"

    async def it_stops_the_container_when_it_never_gets_ready(
        sockets: Path, log: Path, steps: list[str], wait_for_socket: AsyncMock
    ) -> None:
        wait_for_socket.side_effect = RuntimeError("did not start")
        with pytest.raises(RuntimeError, match="did not start"):
            async with start(sockets, log):
                pytest.fail("yielded")
        assert steps == ["stop botbox-credentials-t"]

    async def it_closes_the_stdin_pipe(sockets: Path, log: Path, client: Client) -> None:
        async with start(sockets, log):
            os.fstat(client.stdin)
        with pytest.raises(OSError):
            os.fstat(client.stdin)
