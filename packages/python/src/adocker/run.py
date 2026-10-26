from collections.abc import Sequence
from contextlib import AsyncExitStack

from adocker.Capture import Capture
from adocker.execute import Stream, execute


async def run(
    args: Sequence[str],
    *,
    stdin: Stream,
    stdout: bytearray | Stream,
    stderr: bytearray | Stream,
    limit: int | None = None,
) -> int:
    """Run an attached `docker run` with `args` to its exit and return the client's exit code.

    Files and descriptors pass directly to the client and remain owned by the caller.
    Bytearrays capture output as it arrives, retaining the last `limit` bytes if given.
    The limit does not apply to files or descriptors. A cancel stops the client; the container
    lives on for the caller to remove.
    """
    async with AsyncExitStack() as stack:
        out = (
            await stack.enter_async_context(Capture(stdout, limit))
            if isinstance(stdout, bytearray)
            else stdout
        )
        err = (
            await stack.enter_async_context(Capture(stderr, limit))
            if isinstance(stderr, bytearray)
            else stderr
        )
        return await execute(["run", *args], stdin=stdin, stdout=out, stderr=err)
