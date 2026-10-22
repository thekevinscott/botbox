import asyncio

from botbox.docker.collect import collect
from botbox.docker.finish import finish
from botbox.docker.reap import reap


async def abandon(starting: asyncio.Future[asyncio.subprocess.Process]) -> None:
    """Wait out a spawn whose caller was cancelled, then reap what it started."""
    try:
        process = await starting
    except Exception:
        return
    pipes = (process.stdout, process.stderr)
    readers = [asyncio.ensure_future(collect(pipe, bytearray(), 0)) for pipe in pipes if pipe]
    try:
        await reap(process, *readers)
    finally:
        await finish(process, readers)
