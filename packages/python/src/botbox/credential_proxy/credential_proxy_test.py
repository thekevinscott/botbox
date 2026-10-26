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
    """Image.run: the attached `docker run`, running until cancelled."""

    def __init__(self) -> None:
        self.image = ""
        self.command: tuple[str, ...] = ()
        self.options: dict[str, Any] = {}
        self.stdin: int = -1
        self.container = Mock(name="container")

    def __call__(self, image: str) -> "Client":
        self.image = image
        return self

    async def run(self, *command: str, **options: Any) -> Mock:
        self.command, self.options, self.stdin = command, options, options["stdin"]
        options["stdout"](b"envoy said this\n")
        self.container.name = options["name"]
        self.container.client = asyncio.ensure_future(asyncio.Event().wait())
        return self.container


@pytest.fixture
def steps() -> list[str]:
    return []


@pytest.fixture(autouse=True)
def client() -> Iterator[Client]:
    fake = Client()
    with patch(f"{MODULE}.Image", fake):
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
    async def stop(container: Mock) -> None:
        container.client.cancel()
        steps.append(f"stop {container.name}")

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
            pass
        options = {
            k: v for k, v in client.options.items() if k not in ("stdin", "stdout", "stderr")
        }
        assert options == {
            "name": "botbox-credentials-t",
            "labels": {"botbox.run": "t"},
            "user": "101:101",
            "pid": "container:botbox-proxy-t",
            "network": "bridge",
            "pids_limit": 64,
            "log_driver": "none",
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges"],
            "tmpfs": ["/secrets:uid=101,gid=101,mode=0700"],
            "mounts": [(str(sockets), "/run/botbox", "rw")],
            "entrypoint": "sh",
        }
        assert client.options["stdout"] is client.options["stderr"]

    async def it_writes_the_secret_then_execs_envoy_on_the_config(
        sockets: Path, log: Path, client: Client
    ) -> None:
        async with start(sockets, log):
            pass
        assert client.image == "envoy-image"
        start_script = client.command[1]
        assert client.command == ("-c", start_script, "sh", "/secrets/s.json", "the-config")
        assert start_script.startswith('cat >"$1" && exec envoy ')
        assert start_script.endswith(' --config-yaml "$2"')

    async def it_logs_envoys_output_to_the_file(sockets: Path, log: Path) -> None:
        async with start(sockets, log):
            pass
        assert log.read_bytes() == b"envoy said this\n"

    async def it_waits_for_the_socket_before_yielding(
        sockets: Path, log: Path, steps: list[str], wait_for_socket: AsyncMock, client: Client
    ) -> None:
        async with start(sockets, log):
            steps.append("yielded")
        (socket, waited, waited_log, timeout), _ = wait_for_socket.call_args
        assert (socket, waited_log, timeout) == (sockets / "credentials.sock", log, 30)
        assert waited is client.container.client
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

    def it_takes_the_containers_by_keyword_only(sockets: Path, log: Path) -> None:
        with pytest.raises(TypeError):
            credential_proxy(INJECTION, "s", "botbox-proxy-t", sockets, "t", log)  # type: ignore[arg-type, call-arg]

    async def it_closes_the_stdin_pipe(sockets: Path, log: Path, client: Client) -> None:
        async with start(sockets, log):
            os.fstat(client.stdin)
        with pytest.raises(OSError):
            os.fstat(client.stdin)

    async def it_closes_the_stdin_pipe_when_the_container_will_not_start(
        sockets: Path, log: Path, client: Client, preloaded: Mock
    ) -> None:
        stdins: list[int] = []
        preloaded.side_effect = lambda _: (
            stdins.append(os.open(os.devnull, os.O_RDONLY)) or stdins[0]
        )

        async def refused(*_: str, **__: Any) -> Mock:
            raise RuntimeError("no such image")

        client.run = refused  # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="no such image"):
            async with start(sockets, log):
                pytest.fail("yielded")
        with pytest.raises(OSError):
            os.fstat(stdins[0])
