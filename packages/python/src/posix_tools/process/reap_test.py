import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from .reap import GRACE, reap

TERM, KILL = 15, 9
PROCESS = Mock(pid=4242)
DRAINS = (Mock(name="stdout"), Mock(name="stderr"))


class Group:
    """A process group that ends on the first signal in `ends_on`."""

    def __init__(self, ends_on: set[int]) -> None:
        self.ends_on = ends_on
        self.over = asyncio.Event()

    def signal(self, _pid: int, sig: int) -> None:
        if sig in self.ends_on:
            self.over.set()

    async def ended(self, *_args: object) -> None:
        await self.over.wait()


@pytest.fixture(autouse=True)
def signal() -> Iterator[Mock]:
    with patch(f"{__package__}.reap.signal", autospec=True) as m:
        m.SIGTERM, m.SIGKILL = TERM, KILL
        yield m


@pytest.fixture
async def group() -> Group:
    return Group({TERM})


@pytest.fixture(autouse=True)
def killpg(group: Group) -> Iterator[Mock]:
    with patch(f"{__package__}.reap.os.killpg", autospec=True, side_effect=group.signal) as m:
        yield m


@pytest.fixture(autouse=True)
def ended(group: Group) -> Iterator[AsyncMock]:
    with patch(f"{__package__}.reap.ended", autospec=True, side_effect=group.ended) as m:
        yield m


@pytest.fixture
def timeout() -> Iterator[Mock]:
    with patch(f"{__package__}.reap.asyncio.timeout", side_effect=asyncio.timeout) as m:
        yield m


def describe_reap() -> None:
    def it_gives_the_group_ten_seconds_by_default() -> None:
        assert GRACE == 10

    async def it_waits_the_default_grace(timeout: Mock) -> None:
        await reap(PROCESS)
        timeout.assert_called_once_with(GRACE)

    async def it_gives_the_killed_group_the_grace_again(group: Group, timeout: Mock) -> None:
        group.ends_on = {KILL}
        await reap(PROCESS, grace=0.01)
        assert timeout.call_args_list == [call(0.01), call(0.01)]

    async def it_warns_and_gives_up_on_a_group_that_outlives_the_kill(
        group: Group, killpg: Mock
    ) -> None:
        group.ends_on = set()
        with pytest.warns(
            RuntimeWarning, match="docker's process group 4242 did not stop"
        ) as warned:
            await reap(PROCESS, grace=0.01)
        assert warned[0].filename == __file__
        assert killpg.call_args_list == [call(4242, TERM), call(4242, KILL)]

    async def it_terminates_the_process_group(killpg: Mock) -> None:
        await reap(PROCESS)
        assert killpg.call_args_list == [call(4242, TERM)]

    async def it_starts_with_the_signal_it_is_given(group: Group, killpg: Mock) -> None:
        group.ends_on = {KILL}
        await reap(PROCESS, signum=KILL)
        assert killpg.call_args_list == [call(4242, KILL)]

    async def it_waits_for_the_process_its_drains_and_its_group(ended: AsyncMock) -> None:
        await reap(PROCESS, *DRAINS)
        ended.assert_awaited_once_with(PROCESS, DRAINS)

    async def it_kills_the_group_when_it_outlives_the_grace(
        group: Group, killpg: Mock, ended: AsyncMock
    ) -> None:
        group.ends_on = {KILL}
        await reap(PROCESS, *DRAINS, grace=0.01)
        assert killpg.call_args_list == [call(4242, TERM), call(4242, KILL)]
        assert ended.await_args_list == [call(PROCESS, DRAINS), call(PROCESS, DRAINS)]

    async def it_waits_the_grace_before_killing(group: Group, killpg: Mock) -> None:
        group.ends_on = {KILL}
        task = asyncio.create_task(reap(PROCESS, grace=0.2))
        await asyncio.sleep(0.1)
        assert killpg.call_args_list == [call(4242, TERM)]
        await task

    async def it_tolerates_a_group_that_is_already_gone(group: Group, killpg: Mock) -> None:
        killpg.side_effect = ProcessLookupError
        group.over.set()
        await reap(PROCESS)

    async def it_tolerates_a_group_gone_before_the_kill(group: Group, killpg: Mock) -> None:
        def gone(_pid: int, sig: int) -> None:
            if sig == KILL:
                group.over.set()
                raise ProcessLookupError

        killpg.side_effect = gone
        await reap(PROCESS, grace=0.01)
