import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from botbox.docker.abandon import abandon
from botbox.docker.discard import discard
from botbox.docker.reap import reap
from botbox.docker.settle import settle


@asynccontextmanager
async def tail(path: Path) -> AsyncIterator[asyncio.StreamReader]:
    """Follow a file from its first line and stop the tail process at teardown."""
    starting = asyncio.ensure_future(
        asyncio.create_subprocess_exec(
            "tail",
            "-n",
            "+1",
            "-F",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
    )
    try:
        process = await asyncio.shield(starting)
    except asyncio.CancelledError:
        await settle(abandon(starting))
        raise
    assert process.stdout is not None
    try:
        yield process.stdout
    finally:
        draining = asyncio.ensure_future(discard(process.stdout))
        await settle(reap(process, draining))
