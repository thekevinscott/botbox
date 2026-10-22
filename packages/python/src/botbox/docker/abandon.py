import asyncio

from botbox.docker.reap import reap


async def abandon(starting: asyncio.Future[asyncio.subprocess.Process]) -> None:
    """Wait out a spawn whose caller was cancelled, then stop and reap what it started."""
    try:
        process = await starting
    except Exception:
        return
    pipes = (process.stdout, process.stderr)
    await reap(process, *(asyncio.ensure_future(pipe.read()) for pipe in pipes if pipe))
