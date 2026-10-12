import fcntl
import hashlib
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from tempfile import gettempdir


@contextmanager
def build_lock(tag: str) -> Generator[None]:
    """Hold an exclusive lock on `tag`, shared across processes, for the duration of a build.

    Concurrent `docker build`s of one tag fail: the losers inspect an image id that no longer
    exists. The lock file is keyed by the tag and left in the system temp dir.
    """
    digest = hashlib.sha256(tag.encode()).hexdigest()[:12]
    with (Path(gettempdir()) / f"botbox-build-{digest}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield
