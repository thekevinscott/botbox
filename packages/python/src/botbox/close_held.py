import os
from contextlib import suppress
from typing import IO

HELD: set[IO[bytes]] = set()


def close_held() -> None:
    for pipe in HELD:
        with suppress(OSError):
            pipe.close()
    HELD.clear()


os.register_at_fork(after_in_child=close_held)
