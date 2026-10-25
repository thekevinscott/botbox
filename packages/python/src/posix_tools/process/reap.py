import asyncio
import os
import signal
import warnings
from contextlib import suppress
from typing import Any

from .ended import ended

GRACE = 10


async def reap(
    process: asyncio.subprocess.Process,
    *drains: asyncio.Future[Any],
    grace: float = GRACE,
    signum: int = signal.SIGTERM,
) -> None:
    """Stop `process`'s group and wait it out: `signum`, then SIGKILL, `grace` seconds each.

    `drains` read its pipes. They must keep running until the group is gone: a client blocked
    writing to a full pipe never exits. A group that outlives the SIGKILL is a warning.
    """
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signum)
    try:
        async with asyncio.timeout(grace):
            await ended(process, drains)
    except TimeoutError:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        try:
            async with asyncio.timeout(grace):
                await ended(process, drains)
        except TimeoutError:
            warnings.warn(
                f"docker's process group {process.pid} did not stop", RuntimeWarning, stacklevel=2
            )
