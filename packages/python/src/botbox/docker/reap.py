import asyncio
import os
import signal
from contextlib import suppress
from typing import Any

from botbox.docker.ended import ended

GRACE = 10


async def reap(
    process: asyncio.subprocess.Process, *drains: asyncio.Future[Any], grace: float = GRACE
) -> None:
    """Stop `process`'s group and wait it out: SIGTERM, then SIGKILL, `grace` seconds each.

    `drains` read its pipes. They must keep running until the group is gone: a client blocked
    writing to a full pipe never exits. Raises TimeoutError if the group outlives the SIGKILL.
    """
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        async with asyncio.timeout(grace):
            await ended(process, drains)
    except TimeoutError:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        async with asyncio.timeout(grace):
            await ended(process, drains)
