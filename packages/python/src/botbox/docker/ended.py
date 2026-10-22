import asyncio
import os
from collections.abc import Sequence
from typing import Any

POLL = 0.01


async def ended(process: asyncio.subprocess.Process, drains: Sequence[asyncio.Future[Any]]) -> None:
    """Wait for `process`, the readers of its pipes, and every other member of its group.

    The wait returns as soon as the leader exits, though a descendant may still be running
    and holding the pipes open. The drains are shielded so a timeout here leaves them reading.
    """
    await process.wait()
    await asyncio.gather(*map(asyncio.shield, drains), return_exceptions=True)
    while True:
        try:
            os.killpg(process.pid, 0)
        except OSError:
            return
        await asyncio.sleep(POLL)
