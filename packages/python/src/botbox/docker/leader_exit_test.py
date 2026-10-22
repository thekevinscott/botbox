import asyncio
import os
from collections.abc import Iterator
from unittest.mock import Mock, patch

import pytest

from botbox.docker.leader_exit import leader_exit


@pytest.fixture
def pidfd() -> Iterator[tuple[int, int]]:
    read, write = os.pipe()
    yield read, write
    os.close(write)


@pytest.fixture(autouse=True)
def pidfd_open(pidfd: tuple[int, int]) -> Iterator[Mock]:
    with patch("botbox.docker.leader_exit.os.pidfd_open", autospec=True) as m:
        m.return_value = pidfd[0]
        yield m


@pytest.fixture(autouse=True)
def close() -> Iterator[Mock]:
    with patch("botbox.docker.leader_exit.os.close", autospec=True, side_effect=os.close) as m:
        yield m


def describe_leader_exit() -> None:
    async def it_opens_a_pidfd_for_the_leader(pidfd_open: Mock, pidfd: tuple[int, int]) -> None:
        os.write(pidfd[1], b"x")
        await leader_exit(4242)
        pidfd_open.assert_called_once_with(4242)

    async def it_waits_until_the_pidfd_is_readable(pidfd: tuple[int, int]) -> None:
        task = asyncio.create_task(leader_exit(4242))
        await asyncio.sleep(0.01)
        assert not task.done()
        os.write(pidfd[1], b"x")
        async with asyncio.timeout(1):
            await task

    async def it_stops_watching_and_closes_the_pidfd(pidfd: tuple[int, int], close: Mock) -> None:
        os.write(pidfd[1], b"x")
        await leader_exit(4242)
        close.assert_called_once_with(pidfd[0])
        assert not asyncio.get_running_loop().remove_reader(pidfd[0])

    async def it_cleans_up_when_cancelled(pidfd: tuple[int, int], close: Mock) -> None:
        task = asyncio.create_task(leader_exit(4242))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        close.assert_called_once_with(pidfd[0])

    async def it_tolerates_readiness_reported_twice(pidfd: tuple[int, int]) -> None:
        os.write(pidfd[1], b"x")
        task = asyncio.create_task(leader_exit(4242))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await task

    async def it_returns_at_once_for_a_leader_already_reaped(pidfd_open: Mock, close: Mock) -> None:
        pidfd_open.side_effect = ProcessLookupError
        await leader_exit(4242)
        close.assert_not_called()
