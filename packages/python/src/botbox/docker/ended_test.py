import asyncio
from collections.abc import Iterator
from unittest.mock import Mock, call, patch

import pytest

from botbox.docker.ended import POLL, ended


class Process:
    pid = 4242

    def __init__(self) -> None:
        self.exited = asyncio.Event()
        self.exited.set()

    async def wait(self) -> int:
        await self.exited.wait()
        return 0


@pytest.fixture
async def process() -> Process:
    return Process()


@pytest.fixture(autouse=True)
def killpg() -> Iterator[Mock]:
    with patch("botbox.docker.ended.os.killpg", autospec=True) as m:
        m.side_effect = ProcessLookupError
        yield m


@pytest.fixture
def sleep() -> Iterator[Mock]:
    with patch("botbox.docker.ended.asyncio.sleep", side_effect=asyncio.sleep) as m:
        yield m


def describe_ended() -> None:
    def it_polls_every_10ms() -> None:
        assert POLL == 0.01

    async def it_waits_for_the_process(process: Process) -> None:
        process.exited.clear()
        task = asyncio.create_task(ended(process, ()))  # type: ignore[arg-type]
        await asyncio.sleep(0.01)
        assert not task.done()
        process.exited.set()
        await task

    async def it_waits_for_the_drains(process: Process) -> None:
        drained = asyncio.Event()

        async def drain() -> None:
            await asyncio.sleep(0.01)
            drained.set()

        await ended(process, (asyncio.ensure_future(drain()),))  # type: ignore[arg-type]
        assert drained.is_set()

    async def it_swallows_a_failed_drain(process: Process) -> None:
        async def drain() -> None:
            raise OSError("pipe broke")

        await ended(process, (asyncio.ensure_future(drain()),))  # type: ignore[arg-type]

    async def it_leaves_the_drains_running_when_cancelled(process: Process) -> None:
        release = asyncio.Event()

        async def drain() -> str:
            await release.wait()
            return "read"

        reading = asyncio.ensure_future(drain())
        task = asyncio.create_task(ended(process, (reading,)))  # type: ignore[arg-type]
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        assert await reading == "read"

    async def it_waits_until_the_rest_of_the_group_is_gone(
        process: Process, killpg: Mock, sleep: Mock
    ) -> None:
        killpg.side_effect = [None, None, ProcessLookupError]
        await ended(process, ())  # type: ignore[arg-type]
        assert killpg.call_args_list == [call(4242, 0)] * 3
        assert sleep.call_args_list == [call(POLL)] * 2

    async def it_counts_a_group_it_may_not_signal_as_gone(process: Process, killpg: Mock) -> None:
        killpg.side_effect = PermissionError
        await ended(process, ())  # type: ignore[arg-type]
