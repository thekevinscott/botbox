"""wait_for_socket against real unix sockets."""

import asyncio
import socket as sockets
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from botbox.credential_proxy.wait_for_socket import wait_for_socket


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "c.sock"


@pytest.fixture
def log(tmp_path: Path) -> Path:
    path = tmp_path / "log"
    path.write_text("envoy: starting\n")
    return path


@pytest.fixture
async def client() -> AsyncIterator[asyncio.Future[int]]:
    """A `docker run` client that keeps running."""
    process = await asyncio.create_subprocess_exec("sleep", "60")
    task = asyncio.ensure_future(process.wait())
    yield task
    process.kill()
    await task


def describe_wait_for_socket() -> None:
    async def it_returns_for_a_listening_socket(
        path: Path, log: Path, client: asyncio.Future[int]
    ) -> None:
        server = await asyncio.start_unix_server(lambda _, w: w.close(), path)
        async with server:
            await asyncio.wait_for(wait_for_socket(path, client, log, 5), 1)

    async def it_does_not_take_a_socket_file_with_no_listener(
        path: Path, log: Path, client: asyncio.Future[int]
    ) -> None:
        bound = sockets.socket(sockets.AF_UNIX)
        bound.bind(str(path))
        try:
            with pytest.raises(RuntimeError, match="did not start:\nenvoy: starting"):
                await wait_for_socket(path, client, log, 0.3)
        finally:
            bound.close()

    async def it_times_out_on_a_path_that_never_shows_up(
        path: Path, log: Path, client: asyncio.Future[int]
    ) -> None:
        loop = asyncio.get_running_loop()
        start = loop.time()
        with pytest.raises(RuntimeError, match="did not start"):
            await wait_for_socket(path, client, log, 0.3)
        assert 0.3 <= loop.time() - start < 1

    async def it_waits_for_a_listener_that_starts_late(
        path: Path, log: Path, client: asyncio.Future[int]
    ) -> None:
        bound = sockets.socket(sockets.AF_UNIX)
        bound.bind(str(path))

        async def listen_later() -> None:
            await asyncio.sleep(0.3)
            bound.listen()

        later = asyncio.ensure_future(listen_later())
        try:
            await asyncio.wait_for(wait_for_socket(path, client, log, 5), 2)
            assert later.done()
        finally:
            bound.close()

    async def it_stops_waiting_when_the_client_exits(path: Path, log: Path) -> None:
        process = await asyncio.create_subprocess_exec("false")
        client = asyncio.ensure_future(process.wait())
        with pytest.raises(RuntimeError, match="did not start"):
            await asyncio.wait_for(wait_for_socket(path, client, log, 30), 2)
