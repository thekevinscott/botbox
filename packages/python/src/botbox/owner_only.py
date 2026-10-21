import os
from collections.abc import Generator
from contextlib import contextmanager, suppress
from typing import IO

HELD: set[IO[bytes]] = set()


def close_held() -> None:
    for pipe in HELD:
        with suppress(OSError):
            pipe.close()
    HELD.clear()


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


os.register_at_fork(after_in_child=close_held)
