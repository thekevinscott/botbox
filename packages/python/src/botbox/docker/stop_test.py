import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock, patch

import pytest

from botbox.docker.stop import stop

PROCESS = Mock(pid=4242)


@pytest.fixture(autouse=True)
def reap() -> Iterator[AsyncMock]:
    with patch("botbox.docker.stop.reap", autospec=True) as m:
        yield m


def describe_stop() -> None:
    async def it_reaps_the_process_with_its_drains(reap: AsyncMock) -> None:
        drains = (Mock(), Mock())
        await stop(PROCESS, *drains)
        reap.assert_awaited_once_with(PROCESS, *drains)

    async def it_warns_instead_of_raising_when_the_reap_fails(reap: AsyncMock) -> None:
        reap.side_effect = TimeoutError
        with pytest.warns(RuntimeWarning, match="docker's process group 4242 did not stop"):
            await stop(PROCESS)

    async def it_finishes_the_reap_through_repeated_cancels(reap: AsyncMock) -> None:
        finished = asyncio.Event()

        async def slow(*_args: object) -> None:
            await asyncio.sleep(0.05)
            finished.set()

        reap.side_effect = slow
        task = asyncio.create_task(stop(PROCESS))
        for _ in range(3):
            await asyncio.sleep(0.01)
            task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()
