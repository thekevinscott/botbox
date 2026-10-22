import asyncio
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from botbox.async_build_lock import async_build_lock

WAIT = 0.2


@pytest.fixture(autouse=True)
def lock_dir(tmp_path: Path) -> Iterator[Path]:
    with patch("botbox.async_build_lock.build_lock_path", lambda tag: tmp_path / f"{tag}.lock"):
        yield tmp_path


@pytest.fixture(autouse=True)
def fcntl() -> Iterator[MagicMock]:
    with patch("botbox.async_build_lock.fcntl") as m:
        m.flock.return_value = None
        yield m


def held_elsewhere_for(seconds: float) -> object:
    """An `flock` that finds the lock taken until `seconds` from now."""
    until = time.monotonic() + seconds

    def flock(*_args: object) -> None:
        if time.monotonic() < until:
            raise BlockingIOError

    return flock


def describe_async_build_lock() -> None:
    async def it_locks_the_file_build_lock_path_names_without_blocking(
        fcntl: MagicMock, lock_dir: Path
    ) -> None:
        async with async_build_lock("an-agent:latest"):
            [(lock, flags)] = [c.args for c in fcntl.flock.call_args_list]
            assert Path(lock.name) == lock_dir / "an-agent:latest.lock"
            assert flags == fcntl.LOCK_EX | fcntl.LOCK_NB
            assert not lock.closed

    async def it_tries_again_until_the_lock_is_free(fcntl: MagicMock) -> None:
        fcntl.flock.side_effect = [BlockingIOError, BlockingIOError, None]
        async with async_build_lock("an-agent:latest"):
            assert fcntl.flock.call_count == 3

    async def it_sleeps_50ms_between_tries(fcntl: MagicMock) -> None:
        fcntl.flock.side_effect = [BlockingIOError, BlockingIOError, None]
        with patch("botbox.async_build_lock.asyncio.sleep", autospec=True) as sleep:
            async with async_build_lock("an-agent:latest"):
                assert sleep.await_args_list == [call(0.05), call(0.05)]

    async def it_keeps_the_loop_running_while_it_waits(fcntl: MagicMock) -> None:
        fcntl.flock.side_effect = held_elsewhere_for(WAIT)
        ticks = 0

        async def tick() -> None:
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        ticker = asyncio.create_task(tick())
        async with async_build_lock("an-agent:latest"):
            ticker.cancel()
        assert ticks >= 5

    async def it_closes_the_lock_file_when_cancelled_while_waiting(fcntl: MagicMock) -> None:
        fcntl.flock.side_effect = BlockingIOError
        waiter = asyncio.create_task(async_build_lock("an-agent:latest").__aenter__())
        await asyncio.sleep(WAIT)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert fcntl.flock.call_args.args[0].closed

    async def it_releases_by_closing_the_lock_file_when_the_body_raises(fcntl: MagicMock) -> None:
        with pytest.raises(RuntimeError):
            async with async_build_lock("an-agent:latest"):
                raise RuntimeError("build failed")
        assert fcntl.flock.call_args.args[0].closed
        assert fcntl.flock.call_args_list == [
            call(fcntl.flock.call_args.args[0], fcntl.LOCK_EX | fcntl.LOCK_NB)
        ]
