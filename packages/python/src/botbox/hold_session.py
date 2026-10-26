import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import IO

from adocker.abort_writer import abort_writer
from adocker.Capture import Capture
from adocker.execute import execute
from botbox.agents.agent import SessionAgent
from botbox.process import owner_only, settle
from botbox.Session import Session
from botbox.utils.CapturedLines import CapturedLines
from posix_tools import tail


@asynccontextmanager
async def hold_session(
    agent: SessionAgent, args: list[str], *, output: Path | None = None
) -> AsyncIterator[Session]:
    """Start an attached `docker run` with `args` and yield a session on the agent's CLI in it.

    The client runs as the session's `client` task. Leaving the block stops it if it is still
    running, through any number of cancels; the container lives on for the caller to remove.
    With `output`, the client writes straight to stdout.txt and stderr.txt there, and events
    come from following stdout.txt.
    """
    loop = asyncio.get_running_loop()
    # Created here, not by the spawn, so the write end is owner-only before any fork can copy it.
    read, write = os.pipe()
    pipe = os.fdopen(write, "wb")
    try:
        with pipe, owner_only(pipe):
            transport, protocol = await loop.connect_write_pipe(
                asyncio.streams.FlowControlMixin, pipe
            )
            stdin = asyncio.StreamWriter(transport, protocol, None, loop)
            try:
                async with AsyncExitStack() as stack:
                    out: Capture | IO[bytes]
                    err: Capture | IO[bytes]
                    if output is None:
                        out = await stack.enter_async_context(Capture(bytearray()))
                        err = await stack.enter_async_context(Capture(bytearray()))
                    else:
                        out = stack.enter_context((output / "stdout.txt").open("wb"))
                        err = stack.enter_context((output / "stderr.txt").open("wb"))
                    client = asyncio.ensure_future(
                        execute(["run", *args], stdin=read, stdout=out, stderr=err)
                    )
                    try:
                        if isinstance(out, Capture) and isinstance(err, Capture):
                            yield Session(
                                agent,
                                stdin,
                                out,
                                err.into,
                                client,
                                _readline=CapturedLines(out, client).readline,
                            )
                        else:
                            assert output is not None
                            lines = await stack.enter_async_context(
                                tail(output / "stdout.txt", n=None, follow=True)
                            )
                            yield Session(
                                agent,
                                stdin,
                                None,
                                bytearray(),
                                client,
                                _readline=lambda: anext(lines, b""),
                            )
                    finally:
                        client.cancel()
                        await settle(asyncio.gather(client, return_exceptions=True))
            finally:
                abort_writer(stdin)
    finally:
        os.close(read)
