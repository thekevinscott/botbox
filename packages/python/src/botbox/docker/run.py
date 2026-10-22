import signal
from collections.abc import Sequence

from botbox.docker.Capture import Capture
from botbox.docker.execute import execute
from botbox.docker.spawn import Stream


async def run(
    args: Sequence[str],
    *,
    stdin: Stream,
    stdout: bytearray,
    stderr: bytearray,
    limit: int | None = None,
) -> int:
    """Run an attached `docker run` with `args` to its exit and return the client's exit code.

    The output lands in `stdout` and `stderr` as it arrives, only the last `limit` bytes of
    each if given, so what came before a cancel is kept. The client forwards or swallows
    SIGTERM and keeps waiting for its container, so a cancel kills it outright. The container
    lives on for the caller to remove.
    """
    async with Capture(stdout, limit) as out, Capture(stderr, limit) as err:
        return await execute(
            ["run", *args], stdin=stdin, stdout=out, stderr=err, signum=signal.SIGKILL
        )
