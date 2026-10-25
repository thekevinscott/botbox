import asyncio
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from .child import child


@pytest.fixture
def process() -> Mock:
    return Mock(stdout=None, stderr=None)


@pytest.fixture(autouse=True)
def start(process: Mock) -> Iterator[AsyncMock]:
    with patch(
        f"{__package__}.child.asyncio.create_subprocess_exec", autospec=True, return_value=process
    ) as m:
        yield m


@pytest.fixture(autouse=True)
def close() -> Iterator[AsyncMock]:
    with patch(f"{__package__}.child._close", autospec=True) as m:
        yield m


@pytest.fixture(autouse=True)
def abandon() -> Iterator[AsyncMock]:
    with patch(f"{__package__}.child.abandon", autospec=True) as m:
        yield m


def describe_child() -> None:
    @pytest.mark.parametrize("options", [{}, {"signum": 9, "grace": 0.1, "linger": 2}])
    async def it_starts_a_group_and_passes_cleanup_options(
        start: AsyncMock, process: Mock, close: AsyncMock, options: dict[str, Any]
    ) -> None:
        drains = (asyncio.get_running_loop().create_future(),)
        async with child(
            "program", "arg", stdin=7, stdout=8, stderr=9, drains=drains, **options
        ) as proc:
            assert proc is process
        start.assert_awaited_once_with(
            "program", "arg", stdin=7, stdout=8, stderr=9, start_new_session=True
        )
        expected = {"signum": 15, "grace": 10, "linger": 0} | options
        close.assert_awaited_once_with(process, drains, **expected)

    @pytest.mark.parametrize("error", [ValueError("body"), asyncio.CancelledError()])
    async def it_skips_linger_after_body_errors(
        error: BaseException, close: AsyncMock, process: Mock
    ) -> None:
        with pytest.raises(type(error)):
            async with child("program", linger=2):
                raise error
        close.assert_awaited_once_with(process, (), signum=15, grace=10, linger=0)

    async def it_propagates_spawn_failure_without_cleanup(
        start: AsyncMock, close: AsyncMock, abandon: AsyncMock
    ) -> None:
        start.side_effect = FileNotFoundError("program")
        with pytest.raises(FileNotFoundError):
            async with child("program"):
                pytest.fail("failed spawn entered the body")
        close.assert_not_awaited()
        abandon.assert_not_awaited()

    @pytest.mark.parametrize("repeat", [False, True])
    async def it_waits_out_cancelled_startup_through_repeated_cancels(
        start: AsyncMock, abandon: AsyncMock, close: AsyncMock, process: Mock, repeat: bool
    ) -> None:
        spawned = asyncio.Event()
        release = asyncio.Event()
        cleaning = asyncio.Event()

        async def slow(*_args: object, **_kwargs: object) -> Mock:
            spawned.set()
            await release.wait()
            return process

        async def cleanup(starting: asyncio.Future[object], **options: object) -> None:
            assert options == {"signum": 9, "grace": 0.2}
            cleaning.set()
            assert await starting is process

        async def run() -> None:
            async with child("program", signum=9, grace=0.2):
                pytest.fail("cancelled spawn entered the body")

        start.side_effect = slow
        abandon.side_effect = cleanup
        task = asyncio.create_task(run())
        await spawned.wait()
        task.cancel()
        await cleaning.wait()
        if repeat:
            task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        close.assert_not_awaited()
