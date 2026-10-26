import asyncio
from typing import IO


class FileLines:
    """Lines of a file as another writer appends to it.

    Call `grew` after each append and `end` once nothing more will come. A cancelled
    `readline` loses nothing.
    """

    def __init__(self, file: IO[bytes]) -> None:
        self.file = file
        self.partial = b""
        self.ended = False
        self.appended = asyncio.Event()

    def grew(self) -> None:
        self.appended.set()

    def end(self) -> None:
        self.ended = True
        self.appended.set()

    async def readline(self) -> bytes:
        """The next line, the unterminated rest once ended, then b""."""
        while True:
            self.appended.clear()
            ended = self.ended
            self.partial += self.file.read()
            line, newline, rest = self.partial.partition(b"\n")
            if newline:
                self.partial = rest
                return line + newline
            if ended:
                self.partial = b""
                return line
            await self.appended.wait()
