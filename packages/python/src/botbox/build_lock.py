import fcntl
from collections.abc import Generator
from contextlib import contextmanager

from botbox.build_lock_path import build_lock_path


@contextmanager
def build_lock(tag: str) -> Generator[None]:
    """Hold an exclusive lock on `tag`, shared across processes, for the duration of a build.

    Concurrent `docker build`s of one tag fail: the losers inspect an image id that no longer
    exists.
    """
    with build_lock_path(tag).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield
