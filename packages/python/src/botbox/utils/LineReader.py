import asyncio


class LineReader:
    """Read complete lines without disabling the stream's backpressure."""

    def __init__(self, stream: asyncio.StreamReader) -> None:
        self._stream = stream
        self._chunks: list[bytes] = []

    async def readline(self) -> bytes:
        while True:
            try:
                chunk = await self._stream.readuntil(b"\n")
            except asyncio.LimitOverrunError as error:
                self._chunks.append(await self._stream.readexactly(error.consumed))
                continue
            except asyncio.IncompleteReadError as error:
                chunk = error.partial
            self._chunks.append(chunk)
            line = b"".join(self._chunks)
            self._chunks.clear()
            return line

    def at_eof(self) -> bool:
        return not self._chunks and self._stream.at_eof()
