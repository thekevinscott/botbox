import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any


class FileLines:
    """Lines of a file as another writer appends to it, from `followed`: `tail` following it.

    Call `end` once nothing more will come. `readline` returns every line, then the
    unterminated rest, then b"". A cancelled `readline` loses nothing. Call `close` before
    `followed` stops.
    """

    def __init__(self, path: Path, followed: AsyncIterator[bytes]) -> None:
        self.path = path
        self.followed = followed
        self.read = 0
        self.ended = asyncio.Event()
        self.next: asyncio.Future[bytes] | None = None

    def end(self) -> None:
        self.ended.set()

    async def close(self) -> None:
        if self.next is not None:
            self.next.cancel()
            await asyncio.wait({self.next})

    async def readline(self) -> bytes:
        """The next line, the unterminated rest once ended, then b""."""
        while not self.ended.is_set():
            if self.next is None:
                self.next = asyncio.ensure_future(anext(self.followed, b""))
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
                    await self.ended.wait()
                    continue
                self.read += len(line)
                return line
        with self.path.open("rb") as file:
            file.seek(self.read)
            line = file.readline()
        self.read += len(line)
        return line
