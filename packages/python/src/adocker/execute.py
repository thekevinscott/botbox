import asyncio
from collections.abc import Sequence
from typing import IO, Any

from posix_tools import spawn

from adocker.Capture import Capture

Stream = int | IO[Any] | None


async def execute(
    args: Sequence[str],
    *,
    stdin: Stream,
    stdout: Capture | Stream,
    stderr: Capture | Stream,
) -> int:
    """Run `docker` into the supplied streams and return its exit code once its output is in.

    If this is cancelled or fails first, the client's group is stopped and reaped before the
    error propagates.
    """
    captures = [stream for stream in (stdout, stderr) if isinstance(stream, Capture)]
    try:
        async with spawn(
            "docker",
            *args,
            stdin=stdin,
            stdout=stdout.write if isinstance(stdout, Capture) else stdout,
            stderr=stderr.write if isinstance(stderr, Capture) else stderr,
        ) as process:
            for capture in captures:
                capture.release()
            code = await process.wait()
            await asyncio.gather(*(asyncio.shield(capture.eof) for capture in captures))
    finally:
        for capture in captures:
            capture.release()
    return code
