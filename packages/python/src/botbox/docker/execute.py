import asyncio
import signal
from collections.abc import Sequence

from botbox.docker.Capture import Capture
from botbox.docker.ended import ended
from botbox.docker.exit_code import exit_code
from botbox.docker.reap import reap
from botbox.docker.settle import settle
from botbox.docker.spawn import Stream, spawn

# How long the client's descendants may keep its pipes open after it exits.
LINGER = 2


async def execute(
    args: Sequence[str],
    *,
    stdin: Stream,
    stdout: Capture | Stream,
    stderr: Capture | Stream,
    signum: int = signal.SIGTERM,
) -> int:
    """Run `docker` into the supplied streams and return its exit code.

    If this is cancelled or fails first, the client's group is stopped, starting with `signum`,
    and reaped before the error propagates.
    """
    captures = [stream for stream in (stdout, stderr) if isinstance(stream, Capture)]
    try:
        process = await spawn(
            args,
            stdin=stdin,
            stdout=stdout.write if isinstance(stdout, Capture) else stdout,
            stderr=stderr.write if isinstance(stderr, Capture) else stderr,
        )
    finally:
        for capture in captures:
            capture.release()
    eofs = tuple(capture.eof for capture in captures)
    try:
        code = await exit_code(process)
        async with asyncio.timeout(LINGER):
            await ended(process, eofs)
    except TimeoutError:
        await settle(reap(process, *eofs, signum=signum))
    except BaseException:
        await settle(reap(process, *eofs, signum=signum))
        raise
    return code
