import asyncio
import fcntl
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from botbox.build_lock_path import build_lock_path

POLL = 0.05


@asynccontextmanager
async def async_build_lock(tag: str) -> AsyncGenerator[None]:
    """`build_lock` for the event loop: the same lock file, polled so the loop keeps running.

    A blocking `flock` in a thread can't be cancelled; the thread stays stuck in it.
    """
    with build_lock_path(tag).open("a") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                await asyncio.sleep(POLL)
        yield
