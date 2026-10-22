import asyncio
import os
import signal
from contextlib import suppress
from typing import Any

GRACE = 10


async def reap(
    process: asyncio.subprocess.Process, *drains: asyncio.Future[Any], grace: float = GRACE
) -> None:
    """Stop `process`'s group and wait it out, killing it after `grace` seconds.

    `drains` read its pipes. They must keep running until it exits: a client blocked writing
    to a full pipe never does, and its wait doesn't return until every pipe has closed.
    """
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        async with asyncio.timeout(grace):
            await process.wait()
    except TimeoutError:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        await process.wait()
    await asyncio.gather(*drains, return_exceptions=True)
