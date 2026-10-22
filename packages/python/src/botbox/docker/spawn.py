import asyncio
from collections.abc import Sequence
from typing import IO, Any

Stream = int | IO[Any] | None


async def spawn(
    args: Sequence[str], *, stdin: Stream, stdout: Stream, stderr: Stream
) -> asyncio.subprocess.Process:
    """Start `docker` with `args` as the leader of its own process group."""
    return await asyncio.create_subprocess_exec(
        "docker", *args, stdin=stdin, stdout=stdout, stderr=stderr, start_new_session=True
    )
