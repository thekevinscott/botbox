import asyncio
import fcntl
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from botbox.build_lock_path import build_lock_path

POLL = 0.05


@asynccontextmanager
async def build_lock(tag: str) -> AsyncGenerator[None]:
    """Hold an exclusive lock on `tag`, shared across processes, for the duration of a build.

    Concurrent `docker build`s of one tag fail: the losers inspect an image id that no longer
    exists. The lock file is polled so the loop keeps running: a blocking `flock` in a thread
    can't be cancelled, and the thread stays stuck in it.
    """
    with build_lock_path(tag).open("a") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                await asyncio.sleep(POLL)
        yield
