import asyncio
import signal
from collections.abc import Iterator
from unittest.mock import Mock, call, patch

import pytest

from botbox.docker import reap as module
from botbox.docker.reap import GRACE, reap


class Process:
    """A process group that exits on the first signal in `stops_on`."""

    pid = 4242

    def __init__(self, stops_on: set[int]) -> None:
        self.stops_on = stops_on
        self.exited = asyncio.Event()

    def signal(self, sig: int) -> None:
        if sig in self.stops_on:
            self.exited.set()

    async def wait(self) -> int:
        await self.exited.wait()
        return -15


@pytest.fixture
def killpg() -> Iterator[Mock]:
    with patch("botbox.docker.reap.os.killpg", autospec=True) as m:
        yield m


@pytest.fixture
def process(killpg: Mock) -> Process:
    process = Process({signal.SIGTERM})
    killpg.side_effect = lambda _pid, sig: process.signal(sig)
    return process


def describe_reap() -> None:
    def it_gives_the_group_ten_seconds() -> None:
        assert GRACE == 10

    async def it_terminates_the_process_group(process: Process, killpg: Mock) -> None:
        await reap(process)  # type: ignore[arg-type]
        assert killpg.call_args_list == [call(4242, signal.SIGTERM)]

    async def it_kills_the_group_when_it_outlives_the_grace(process: Process, killpg: Mock) -> None:
        process.stops_on = {signal.SIGKILL}
        with patch.object(module, "GRACE", 0.01):
            await reap(process)  # type: ignore[arg-type]
        assert killpg.call_args_list == [call(4242, signal.SIGTERM), call(4242, signal.SIGKILL)]

    async def it_waits_the_grace_before_killing(process: Process, killpg: Mock) -> None:
        process.stops_on = {signal.SIGKILL}
        with patch.object(module, "GRACE", 0.2):
            task = asyncio.create_task(reap(process))  # type: ignore[arg-type]
            await asyncio.sleep(0.1)
            assert killpg.call_args_list == [call(4242, signal.SIGTERM)]
            await task

    async def it_tolerates_a_group_that_is_already_gone(process: Process, killpg: Mock) -> None:
        killpg.side_effect = ProcessLookupError
        process.exited.set()
        await reap(process)  # type: ignore[arg-type]

    async def it_tolerates_a_group_gone_before_the_kill(process: Process, killpg: Mock) -> None:
        def gone(_pid: int, sig: int) -> None:
            if sig == signal.SIGKILL:
                process.exited.set()
                raise ProcessLookupError

        killpg.side_effect = gone
        with patch.object(module, "GRACE", 0.01):
            await reap(process)  # type: ignore[arg-type]

    async def it_waits_for_the_drains_to_finish(process: Process) -> None:
        drained = asyncio.Event()

        async def drain() -> None:
            await process.exited.wait()
            await asyncio.sleep(0.01)
            drained.set()

        await reap(process, asyncio.ensure_future(drain()))  # type: ignore[arg-type]
        assert drained.is_set()

    async def it_swallows_a_failed_drain(process: Process) -> None:
        async def drain() -> None:
            raise OSError("pipe broke")

        await reap(process, asyncio.ensure_future(drain()))  # type: ignore[arg-type]
