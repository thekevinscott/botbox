import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from botbox.docker.abandon import abandon
from botbox.docker.discard import discard
from botbox.docker.reap import reap
from botbox.docker.settle import settle
from botbox.owner_only import owner_only


@asynccontextmanager
async def tail(path: Path) -> AsyncIterator[asyncio.StreamReader]:
    """Follow a file until teardown or the owner closes its lifetime pipe."""
    read, write = os.pipe()
    try:
        with os.fdopen(write, "wb") as lifetime, owner_only(lifetime):
            starting = asyncio.ensure_future(
                asyncio.create_subprocess_exec(
                    "sh",
                    "-c",
                    'tail -n +1 -F "$1" & child=$!; read _; kill "$child"; wait "$child"',
                    "sh",
                    str(path),
                    stdin=read,
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
    finally:
        os.close(read)
