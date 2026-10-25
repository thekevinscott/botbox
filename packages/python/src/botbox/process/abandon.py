import asyncio

from .discard import discard
from .reap import reap


async def abandon(starting: asyncio.Future[asyncio.subprocess.Process]) -> None:
    """Wait out a spawn whose caller was cancelled, then reap what it started."""
    try:
        process = await starting
    except Exception:
        return
    pipes = (process.stdout, process.stderr)
    readers = [asyncio.ensure_future(discard(pipe)) for pipe in pipes if pipe]
    try:
        await reap(process, *readers)
    finally:
        for reader in readers:
            reader.cancel()
        await asyncio.gather(*readers, return_exceptions=True)
