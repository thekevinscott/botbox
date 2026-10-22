import asyncio
from collections.abc import Sequence
from typing import Any

from botbox.docker.exit_code import exit_code
from botbox.docker.group_running import group_running

POLL = 0.01


async def ended(process: asyncio.subprocess.Process, drains: Sequence[asyncio.Future[Any]]) -> None:
    """Wait for `process`, the readers of its pipes, and every other member of its group.

    The drains are shielded, so a timeout around this leaves them reading.
    """
    await exit_code(process)
    await asyncio.gather(*map(asyncio.shield, drains), return_exceptions=True)
    while group_running(process.pid):
        await asyncio.sleep(POLL)
