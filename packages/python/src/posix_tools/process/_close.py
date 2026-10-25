import asyncio
from collections.abc import Sequence
from typing import Any

from .discard import discard
from .ended import ended
from .group_running import group_running
from .reap import reap
from .settle import settle


async def _close(
    process: asyncio.subprocess.Process,
    drains: Sequence[asyncio.Future[Any]],
    signum: int,
    grace: float,
    linger: float,
) -> None:
    if process.stdin is not None:
        process.stdin.close()
    readers = [
        asyncio.ensure_future(discard(pipe))
        for pipe in (process.stdout, process.stderr)
        if pipe is not None
    ]
    finished = False
    try:
        if linger:
            try:
                async with asyncio.timeout(linger):
                    await ended(process, (*drains, *readers))
                finished = True
            except TimeoutError:
                # The natural-exit window expired; stop the remaining group below.
                pass
    finally:
        try:
            finished = finished or (
                process.returncode is not None
                and not group_running(process.pid)
                and all(drain.done() for drain in (*drains, *readers))
            )
            if not finished:
                await settle(reap(process, *drains, *readers, signum=signum, grace=grace))
        finally:
            for reader in readers:
                reader.cancel()
            await settle(asyncio.gather(*readers, return_exceptions=True))
