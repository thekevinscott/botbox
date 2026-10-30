import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from botbox.credential_proxy.wait_for_socket import wait_for_socket

SOCKET = "/run/botbox/c.sock"


class DockerException(Exception):
    pass


@pytest.fixture(autouse=True)
def docker_exception() -> Iterator[None]:
    with patch(f"{__package__}.wait_for_socket.DockerException", DockerException):
        yield


class Through:
    """A container whose socat probe fails until `ready`."""

    def __init__(self) -> None:
        self.ready = False
        self.calls: list[tuple[str, ...]] = []

    async def exec(self, *command: str, **_: Any) -> None:
        self.calls.append(command)
        if not self.ready:
            raise DockerException("connect: No such file or directory")


@pytest.fixture
def through() -> Through:
    return Through()


@pytest.fixture
def log(tmp_path: Path) -> Path:
    path = tmp_path / "log"
    path.write_bytes(b"envoy said this\n")
    return path


@pytest.fixture
async def running() -> AsyncIterator[asyncio.Future[int]]:
    client: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    yield client
    client.cancel()


def wait(through: Through, client: asyncio.Future[int], log: Path, timeout: float) -> Any:
    return wait_for_socket(through, SOCKET, client, log, timeout)  # type: ignore[arg-type]


def describe_wait_for_socket() -> None:
    async def it_connects_to_the_socket_with_socat(
        through: Through, log: Path, running: asyncio.Future[int]
    ) -> None:
        through.ready = True
        await wait(through, running, log, 5)
        assert through.calls == [("socat", "-u", "OPEN:/dev/null", f"UNIX-CONNECT:{SOCKET}")]

    async def it_waits_for_a_socket_that_comes_later(
        through: Through, log: Path, running: asyncio.Future[int]
    ) -> None:
        loop = asyncio.get_running_loop()
        start = loop.time()
        loop.call_later(0.1, setattr, through, "ready", True)
        await wait(through, running, log, 5)
        assert loop.time() - start < 0.5

    async def it_polls_every_50ms(
        through: Through, log: Path, running: asyncio.Future[int]
    ) -> None:
        with pytest.raises(RuntimeError):
            await wait(through, running, log, 0.5)
        assert 5 <= len(through.calls) <= 15

    async def it_raises_with_the_log_when_the_client_exits(through: Through, log: Path) -> None:
        client: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        client.set_result(1)
        with pytest.raises(RuntimeError, match=r"did not start:\nenvoy said this\n$"):
            await wait(through, client, log, 5)

    async def it_chains_the_clients_failure(through: Through, log: Path) -> None:
        client: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        client.set_exception(OSError("no docker"))
        with pytest.raises(RuntimeError) as error:
            await wait(through, client, log, 5)
        assert str(error.value.__cause__) == "no docker"

    async def it_gives_up_after_the_timeout(
        through: Through, log: Path, running: asyncio.Future[int]
    ) -> None:
        loop = asyncio.get_running_loop()
        start = loop.time()
        with pytest.raises(RuntimeError, match="did not start") as error:
            await wait(through, running, log, 0.2)
        assert loop.time() - start >= 0.2
        assert error.value.__cause__ is None

    async def it_keeps_polling_at_the_deadline_and_gives_up_past_it(
        through: Through, log: Path, running: asyncio.Future[int]
    ) -> None:
        with (
            patch(f"{__package__}.wait_for_socket.time") as clock,
            pytest.raises(RuntimeError, match="did not start"),
        ):
            clock.monotonic.side_effect = [100.0, 105.0, 105.5]
            await wait(through, running, log, 5)
        assert len(through.calls) == 2

    async def it_keeps_only_the_end_of_a_long_log(through: Through, log: Path) -> None:
        log.write_bytes(b"a" * 10 + b"b" * 65536)
        client: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        client.set_result(1)
        with pytest.raises(RuntimeError) as error:
            await wait(through, client, log, 5)
        assert str(error.value).endswith(":\n" + "b" * 65536)
