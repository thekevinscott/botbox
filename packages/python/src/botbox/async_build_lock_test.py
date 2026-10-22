import asyncio
import fcntl
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from botbox.async_build_lock import async_build_lock

WAIT = 0.2


@pytest.fixture(autouse=True)
def lock_dir(tmp_path: Path) -> Iterator[Path]:
    with patch("botbox.async_build_lock.build_lock_path", lambda tag: tmp_path / f"{tag}.lock"):
        yield tmp_path


def try_lock(path: Path) -> bool:
    with path.open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True


async def hold(tag: str, held: asyncio.Event, release: asyncio.Event) -> None:
    async with async_build_lock(tag):
        held.set()
        await release.wait()


def describe_async_build_lock() -> None:
    async def it_locks_the_file_build_lock_path_names(lock_dir: Path) -> None:
        async with async_build_lock("an-agent:latest"):
            assert not try_lock(lock_dir / "an-agent:latest.lock")
        assert try_lock(lock_dir / "an-agent:latest.lock")

    async def it_makes_a_second_holder_of_the_same_tag_wait_until_released() -> None:
        held, release = asyncio.Event(), asyncio.Event()
        holder = asyncio.create_task(hold("an-agent:latest", held, release))
        await held.wait()
        second, never = asyncio.Event(), asyncio.Event()
        waiter = asyncio.create_task(hold("an-agent:latest", second, never))
        await asyncio.sleep(WAIT)
        assert not second.is_set()
        release.set()
        await asyncio.wait_for(second.wait(), WAIT * 10)
        never.set()
        await asyncio.gather(holder, waiter)

    async def it_does_not_make_a_different_tag_wait() -> None:
        held, release = asyncio.Event(), asyncio.Event()
        holder = asyncio.create_task(hold("an-agent:latest", held, release))
        await held.wait()
        async with asyncio.timeout(WAIT * 10), async_build_lock("another-agent:latest"):
            pass
        release.set()
        await holder

    async def it_waits_on_a_lock_held_elsewhere_without_blocking_the_loop(lock_dir: Path) -> None:
        locked, ticks = threading.Event(), 0

        def hold_elsewhere() -> None:
            with (lock_dir / "an-agent:latest.lock").open("a") as other:
                fcntl.flock(other, fcntl.LOCK_EX)
                locked.set()
                time.sleep(WAIT)

        async def tick() -> None:
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        elsewhere = threading.Thread(target=hold_elsewhere)
        elsewhere.start()
        locked.wait()
        ticker = asyncio.create_task(tick())
        async with async_build_lock("an-agent:latest"):
            ticker.cancel()
        elsewhere.join()
        assert ticks >= 5

    async def it_lets_go_when_cancelled_while_waiting(lock_dir: Path) -> None:
        held, release = asyncio.Event(), asyncio.Event()
        holder = asyncio.create_task(hold("an-agent:latest", held, release))
        await held.wait()
        never = asyncio.Event()
        waiter = asyncio.create_task(hold("an-agent:latest", asyncio.Event(), never))
        await asyncio.sleep(WAIT)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        release.set()
        await holder
        assert try_lock(lock_dir / "an-agent:latest.lock")

    async def it_releases_when_the_body_raises(lock_dir: Path) -> None:
        with pytest.raises(RuntimeError):
            async with async_build_lock("an-agent:latest"):
                raise RuntimeError("build failed")
        assert try_lock(lock_dir / "an-agent:latest.lock")
