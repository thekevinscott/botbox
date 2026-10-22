import asyncio
from collections.abc import Sequence

from botbox.docker.spawn import Stream, spawn


async def run(
    args: Sequence[str], *, stdin: Stream, stdout: Stream, stderr: Stream
) -> asyncio.subprocess.Process:
    """Start an attached `docker run` with `args` and hand back its client.

    The caller owns it: stop it with `reap`, and keep reading any piped output until it exits.
    """
    return await spawn(["run", *args], stdin=stdin, stdout=stdout, stderr=stderr)
