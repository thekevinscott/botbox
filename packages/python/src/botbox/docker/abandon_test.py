import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock, patch

import pytest

from botbox.docker.abandon import abandon


def stream(data: bytes) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


@pytest.fixture(autouse=True)
def stop() -> Iterator[AsyncMock]:
    with patch("botbox.docker.abandon.stop", autospec=True) as m:
        yield m


def started(process: object) -> asyncio.Future[object]:
    future: asyncio.Future[object] = asyncio.get_running_loop().create_future()
    future.set_result(process)
    return future


def describe_abandon() -> None:
    async def it_stops_what_the_spawn_started_while_draining_its_pipes(stop: AsyncMock) -> None:
        process = Mock(stdout=stream(b"out"), stderr=stream(b"err"))
        await abandon(started(process))  # type: ignore[arg-type]
        stopped, *drains = stop.await_args_list[0].args
        assert stopped is process
        assert [await drain for drain in drains] == [b"out", b"err"]

    async def it_drains_only_the_pipes_there_are(stop: AsyncMock) -> None:
        process = Mock(stdout=None, stderr=stream(b"err"))
        await abandon(started(process))  # type: ignore[arg-type]
        _, *drains = stop.await_args_list[0].args
        assert [await drain for drain in drains] == [b"err"]

    async def it_waits_for_the_spawn_to_finish(stop: AsyncMock) -> None:
        starting: asyncio.Future[object] = asyncio.get_running_loop().create_future()
        task = asyncio.create_task(abandon(starting))  # type: ignore[arg-type]
        await asyncio.sleep(0.01)
        stop.assert_not_awaited()
        starting.set_result(Mock(stdout=None, stderr=None))
        await task
        stop.assert_awaited_once()

    async def it_has_nothing_to_stop_when_the_spawn_failed(stop: AsyncMock) -> None:
        starting: asyncio.Future[object] = asyncio.get_running_loop().create_future()
        starting.set_exception(FileNotFoundError("docker"))
        await abandon(starting)  # type: ignore[arg-type]
        stop.assert_not_awaited()
