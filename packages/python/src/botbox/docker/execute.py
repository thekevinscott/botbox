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
    stdout: Capture,
    stderr: Capture,
    signum: int = signal.SIGTERM,
) -> int:
    """Run `docker` with `args` to its exit, its output into the captures, and return its code.

    If this is cancelled or fails first, the client's group is stopped, starting with `signum`,
    and reaped before the error propagates.
    """
    try:
        process = await spawn(args, stdin=stdin, stdout=stdout.write, stderr=stderr.write)
    finally:
        stdout.release()
        stderr.release()
    eofs = (stdout.eof, stderr.eof)
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
