import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from botbox.posix_tools.process.ended import POLL, ended

PROCESS = Mock(pid=4242)


@pytest.fixture(autouse=True)
def exit_code() -> Iterator[AsyncMock]:
    with patch("botbox.posix_tools.process.ended.exit_code", autospec=True) as m:
        yield m


@pytest.fixture(autouse=True)
def group_running() -> Iterator[Mock]:
    with patch(
        "botbox.posix_tools.process.ended.group_running", autospec=True, return_value=False
    ) as m:
        yield m


@pytest.fixture
def sleep() -> Iterator[Mock]:
    with patch("botbox.posix_tools.process.ended.asyncio.sleep", side_effect=asyncio.sleep) as m:
        yield m


def describe_ended() -> None:
    def it_polls_every_10ms() -> None:
        assert POLL == 0.01

    async def it_waits_for_the_leader_to_exit(exit_code: AsyncMock) -> None:
        exited = asyncio.Event()

        async def leader(_process: object) -> int:
            await exited.wait()
            return 0

        exit_code.side_effect = leader
        task = asyncio.create_task(ended(PROCESS, ()))
        await asyncio.sleep(0.01)
        assert not task.done()
        exited.set()
        await task
        exit_code.assert_awaited_once_with(PROCESS)

    async def it_waits_for_the_drains() -> None:
        drained = asyncio.Event()

        async def drain() -> None:
            await asyncio.sleep(0.01)
            drained.set()

        await ended(PROCESS, (asyncio.ensure_future(drain()),))
        assert drained.is_set()

    async def it_swallows_a_failed_drain() -> None:
        async def drain() -> None:
            raise OSError("pipe broke")

        await ended(PROCESS, (asyncio.ensure_future(drain()),))

    async def it_leaves_the_drains_running_when_cancelled() -> None:
        release = asyncio.Event()

        async def drain() -> str:
            await release.wait()
            return "read"

        reading = asyncio.ensure_future(drain())
        task = asyncio.create_task(ended(PROCESS, (reading,)))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        assert await reading == "read"

    async def it_waits_until_no_one_else_in_the_group_runs(
        group_running: Mock, sleep: Mock
    ) -> None:
        group_running.side_effect = [True, True, False]
        await ended(PROCESS, ())
        assert group_running.call_args_list == [call(4242)] * 3
        assert sleep.call_args_list == [call(POLL)] * 2
