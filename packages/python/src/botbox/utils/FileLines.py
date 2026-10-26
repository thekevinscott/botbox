import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any


class FileLines:
    """Lines of a file as another writer appends to it, from `followed`: `tail` following it.

    Call `grew` with each append's size and `end` once nothing more will come. `readline`
    returns every line, then the unterminated rest, then b"". A cancelled `readline` loses
    nothing. Call `close` before `followed` stops.
    """

    def __init__(self, path: Path, followed: AsyncIterator[bytes]) -> None:
        self.path = path
        self.followed = followed
        self.written = 0
        self.read = 0
        self.ended = asyncio.Event()
        self.next: asyncio.Future[bytes] | None = None

    def grew(self, size: int) -> None:
        self.written += size

    def end(self) -> None:
        self.ended.set()

    async def close(self) -> None:
        if self.next is not None:
            self.next.cancel()
            await asyncio.wait({self.next})

    async def readline(self) -> bytes:
        """The next line, the unterminated rest once ended, then b""."""
        while self.read < self.written or not self.ended.is_set():
            if self.next is None:
                self.next = asyncio.ensure_future(anext(self.followed, b""))
            if self.ended.is_set():
                rest = self.unterminated()
                if rest is not None:
                    self.read = self.written
                    return rest
                await asyncio.wait({self.next})
            else:
                ended = asyncio.ensure_future(self.ended.wait())
                racing: set[asyncio.Future[Any]] = {self.next, ended}
                try:
                    await asyncio.wait(racing, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    ended.cancel()
            if self.next.done():
                line = self.next.result()
                self.next = None
                if not line:
                    break
                self.read += len(line)
                return line
        return b""

    def unterminated(self) -> bytes | None:
        """What is left past the lines read, if it holds no whole line."""
        with self.path.open("rb") as file:
            file.seek(self.read)
            rest = file.readline()
        return None if rest.endswith(b"\n") else rest
