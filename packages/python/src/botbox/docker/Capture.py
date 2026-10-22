import asyncio
import os
from types import TracebackType


class Capture(asyncio.Protocol):
    """A pipe whose output lands in `into`, keeping only its last `limit` bytes if given.

    Hand `write` to a child, then `release` it. `grew` is set each time bytes land, and `eof`
    resolves when the pipe closes. Leaving the context closes the pipe, though a child that
    escaped its group still holds the write end. `into` belongs to the caller, so what was read
    outlasts the pipe.
    """

    def __init__(self, into: bytearray, limit: int | None = None) -> None:
        self.into = into
        self.limit = limit
        self.grew = asyncio.Event()
        self.eof: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    async def __aenter__(self) -> "Capture":
        read, self.write = os.pipe()
        self.released = False
        pipe = os.fdopen(read, "rb")
        try:
            self.transport, _ = await asyncio.get_running_loop().connect_read_pipe(
                lambda: self, pipe
            )
        except BaseException:
            pipe.close()
            self.release()
            raise
        return self

    async def __aexit__(
        self,
        _type: type[BaseException] | None,
        _error: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.release()
        self.transport.close()

    def release(self) -> None:
        if not self.released:
            self.released = True
            os.close(self.write)

    def data_received(self, data: bytes) -> None:
        self.into += data
        if self.limit is not None:
            del self.into[: max(len(self.into) - self.limit, 0)]
        self.grew.set()

    def connection_lost(self, _error: Exception | None) -> None:
        self.eof.set_result(None)
