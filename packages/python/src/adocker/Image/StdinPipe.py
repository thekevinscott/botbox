import asyncio
import os
from contextlib import suppress
from typing import IO

HELD: set[IO[bytes]] = set()


def close_held() -> None:
    """Close every held write end in a forked child, so only the parent keeps them open.

    A forked worker inherits every descriptor, and close-on-exec doesn't apply without an exec.
    """
    for pipe in HELD:
        with suppress(OSError):
            pipe.close()
    HELD.clear()


os.register_at_fork(after_in_child=close_held)


class StdinPipe:
    """A pipe for a client's stdin: `read` for the client, `writer` for this process alone.

    Its write end is closed in every child forked while it is held, until `release`, which
    also closes `read`. Closing `writer` is the caller's.
    """

    def __init__(self, read: int, pipe: IO[bytes], writer: asyncio.StreamWriter) -> None:
        self.read = read
        self.pipe = pipe
        self.writer = writer

    @classmethod
    async def open(cls) -> "StdinPipe":
        loop = asyncio.get_running_loop()
        read, write = os.pipe()
        pipe = os.fdopen(write, "wb")
        HELD.add(pipe)
        try:
            transport, protocol = await loop.connect_write_pipe(
                asyncio.streams.FlowControlMixin, pipe
            )
        except BaseException:
            HELD.discard(pipe)
            pipe.close()
            os.close(read)
            raise
        return cls(read, pipe, asyncio.StreamWriter(transport, protocol, None, loop))

    def release(self) -> None:
        HELD.discard(self.pipe)
        os.close(self.read)
