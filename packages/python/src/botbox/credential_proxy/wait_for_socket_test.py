import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest

from botbox.credential_proxy.wait_for_socket import wait_for_socket


@pytest.fixture
def socket(tmp_path: Path) -> Path:
    return tmp_path / "c.sock"


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


async def serve(socket: Path) -> asyncio.Server:
    return await asyncio.start_unix_server(lambda _, w: w.close(), socket)


def describe_wait_for_socket() -> None:
    async def it_returns_once_the_socket_accepts(
        socket: Path, log: Path, running: asyncio.Future[int]
    ) -> None:
        server = await serve(socket)
        try:
            await wait_for_socket(socket, running, log, 5)
        finally:
            server.close()

    async def it_waits_for_a_socket_that_comes_later(
        socket: Path, log: Path, running: asyncio.Future[int]
    ) -> None:
        loop = asyncio.get_running_loop()
        start = loop.time()
        later = loop.call_later(0.1, asyncio.ensure_future, serve(socket))
        await wait_for_socket(socket, running, log, 5)
        later.cancel()
        assert loop.time() - start < 0.5

    async def it_polls_every_50ms(socket: Path, log: Path, running: asyncio.Future[int]) -> None:
        with (
            patch.object(
                asyncio, "open_unix_connection", wraps=asyncio.open_unix_connection
            ) as attempts,
            pytest.raises(RuntimeError),
        ):
            await wait_for_socket(socket, running, log, 0.5)
        assert 5 <= attempts.call_count <= 15

    async def it_does_not_take_a_file_that_refuses_connections(
        socket: Path, log: Path, running: asyncio.Future[int]
    ) -> None:
        socket.touch()
        with pytest.raises(RuntimeError, match="did not start"):
            await wait_for_socket(socket, running, log, 0.1)

    async def it_raises_with_the_log_when_the_client_exits(socket: Path, log: Path) -> None:
        client: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        client.set_result(1)
        with pytest.raises(RuntimeError, match=r"did not start:\nenvoy said this\n$"):
            await wait_for_socket(socket, client, log, 5)

    async def it_chains_the_clients_failure(socket: Path, log: Path) -> None:
        client: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        client.set_exception(OSError("no docker"))
        with pytest.raises(RuntimeError) as error:
            await wait_for_socket(socket, client, log, 5)
        assert str(error.value.__cause__) == "no docker"

    async def it_gives_up_after_the_timeout(
        socket: Path, log: Path, running: asyncio.Future[int]
    ) -> None:
        loop = asyncio.get_running_loop()
        start = loop.time()
        with pytest.raises(RuntimeError, match="did not start") as error:
            await wait_for_socket(socket, running, log, 0.2)
        assert loop.time() - start >= 0.2
        assert error.value.__cause__ is None

    async def it_keeps_only_the_end_of_a_long_log(socket: Path, log: Path) -> None:
        log.write_bytes(b"a" * 10 + b"b" * 65536)
        client: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        client.set_result(1)
        with pytest.raises(RuntimeError) as error:
            await wait_for_socket(socket, client, log, 5)
        assert str(error.value).endswith(":\n" + "b" * 65536)
