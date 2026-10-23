import asyncio
import os
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from botbox.agents.agent import SessionAgent
from botbox.docker.abort_writer import abort_writer
from botbox.docker.execute import execute
from botbox.docker.settle import settle
from botbox.owner_only import owner_only
from botbox.Session import Session
from botbox.tail import tail


@asynccontextmanager
async def hold_session(
    agent: SessionAgent, args: list[str], output: Path
) -> AsyncIterator[Session]:
    """Start an attached `docker run` with `args` and yield a session on the agent's CLI in it.

    The client runs as the session's `client` task. Leaving the block kills it if it is still
    running, through any number of cancels; the container lives on for the caller to remove.
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
                with (
                    (output / "stdout.txt").open("wb") as out,
                    (output / "stderr.txt").open("wb") as err,
                ):
                    async with tail(output / "stdout.txt") as reader:
                        # SIGKILL, as `docker.run` does: the client outlives SIGTERM.
                        client = asyncio.ensure_future(
                            execute(
                                ["run", *args],
                                stdin=read,
                                stdout=out,
                                stderr=err,
                                signum=signal.SIGKILL,
                            )
                        )
                        try:
                            yield Session(agent, stdin, reader, client)
                        finally:
                            client.cancel()
                            await settle(asyncio.gather(client, return_exceptions=True))
            finally:
                abort_writer(stdin)
    finally:
        os.close(read)
