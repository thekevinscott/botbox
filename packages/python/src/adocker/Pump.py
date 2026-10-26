import asyncio
import os
from collections.abc import Callable
from types import TracebackType

type Sink = Callable[[bytes], object]


class Pump(asyncio.Protocol):
    """A pipe whose output goes to `sink` chunk by chunk, as it arrives. Nothing is kept.

    Hand `write` to a child, then `release` it. `eof` resolves when the pipe closes, or raises
    what `sink` raised, which also closes the pipe. Leaving the context closes the pipe, though
    a child that escaped its group still holds the write end.
    """

    def __init__(self, sink: Sink) -> None:
        self.sink = sink
        self.eof: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    async def __aenter__(self) -> "Pump":
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
        try:
            self.sink(data)
        except Exception as error:
            self.eof.set_exception(error)
            self.transport.close()

    def connection_lost(self, _error: Exception | None) -> None:
        if not self.eof.done():
            self.eof.set_result(None)
