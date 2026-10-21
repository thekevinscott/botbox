from collections.abc import Generator
from contextlib import contextmanager
from typing import IO

from botbox.close_held import HELD


@contextmanager
def owner_only(pipe: IO[bytes]) -> Generator[None]:
    """Close `pipe` in every child forked while it is held, so only this process keeps it open.

    A forked worker inherits every descriptor, and close-on-exec doesn't apply without an exec.
    """
    HELD.add(pipe)
    try:
        yield
    finally:
        HELD.discard(pipe)
