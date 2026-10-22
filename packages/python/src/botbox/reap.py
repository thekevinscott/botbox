import re

from botbox.reap_run import reap_run
from botbox.run_dir import run_dir

LOCK = re.compile(r"[0-9a-f]{12}\.lock")


async def reap() -> list[str]:
    """Remove what runs whose owner died left behind, and return their tokens.

    Each run holds a lock for its whole life, and the kernel drops it however the owner dies,
    SIGKILL included. A run whose lock is free loses its containers, labelled
    `botbox.run=<token>`, and its temp home with the credentials staged in it. Every run and
    session sweeps when it starts; call this to sweep without starting one.

    Only this user's runs are swept, on the daemon `docker` reaches now. A run it can't clear
    is a `RuntimeWarning`, and is tried again on the next sweep.
    """
    reaped = []
    for lock in sorted(run_dir().iterdir()):
        if LOCK.fullmatch(lock.name) and await reap_run(lock):
            reaped.append(lock.stem)
    return reaped
