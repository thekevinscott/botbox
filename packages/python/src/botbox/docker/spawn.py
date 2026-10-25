import asyncio
from collections.abc import Sequence
from typing import IO, Any

from botbox.posix_tools.process.abandon import abandon
from botbox.posix_tools.process.settle import settle

Stream = int | IO[Any] | None


async def spawn(
    args: Sequence[str], *, stdin: Stream, stdout: Stream, stderr: Stream
) -> asyncio.subprocess.Process:
    """Start `docker` with `args` as the leader of its own process group.

    A cancel can land after docker has started but before its handle comes back, and asyncio
    would then kill only the leader. So the start is shielded and, if cancelled, reaped.
    """
    starting = asyncio.ensure_future(
        asyncio.create_subprocess_exec(
            "docker", *args, stdin=stdin, stdout=stdout, stderr=stderr, start_new_session=True
        )
    )
    try:
        return await asyncio.shield(starting)
    except asyncio.CancelledError:
        await settle(abandon(starting))
        raise
