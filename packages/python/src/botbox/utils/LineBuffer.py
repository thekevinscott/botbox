from collections import deque
from collections.abc import Iterator
from typing import Self


class LineBuffer:
    """Bytes added with `+=` come out of iterating it as whole lines, each once.

    Iterating yields the lines complete so far and stops. Once closed, the unterminated rest
    comes out last.
    """

    def __init__(self) -> None:
        self.lines: deque[bytes] = deque()
        self.rest: list[bytes] = []

    def __iadd__(self, chunk: bytes) -> Self:
        *lines, rest = chunk.split(b"\n")
        if lines:
            lines[0] = b"".join([*self.rest, lines[0]])
            self.rest = []
        self.lines.extend(line + b"\n" for line in lines)
        if rest:
            self.rest.append(rest)
        return self

    def __iter__(self) -> Iterator[bytes]:
        while self.lines:
            yield self.lines.popleft()

    def close(self) -> None:
        if self.rest:
            self.lines.append(b"".join(self.rest))
            self.rest = []
