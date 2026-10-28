from collections.abc import Callable
from types import TracebackType
from typing import Self


class LineFilter:
    """A sink that hands `sink` each line of the chunks it is called with, through `keep`.

    A line is passed to `keep` whole, with its trailing newline, however the chunks split it.
    What `keep` returns goes to `sink`; None drops the line. `close`, or leaving the block,
    passes the unterminated rest through `keep` too. An error from `keep` propagates to the
    caller, and the line it was given is not written.
    """

    def __init__(
        self, sink: Callable[[bytes], None], keep: Callable[[bytes], bytes | None]
    ) -> None:
        self.sink = sink
        self.keep = keep
        self.pending: list[bytes] = []

    def __call__(self, chunk: bytes) -> None:
        start = 0
        while (end := chunk.find(b"\n", start) + 1) > 0:
            self.pending.append(chunk[start:end])
            self._line()
            start = end
        self.pending.append(chunk[start:])

    def close(self) -> None:
        self._line()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _line(self) -> None:
        line = b"".join(self.pending)
        self.pending = []
        if line:
            kept = self.keep(line)
            if kept is not None:
                self.sink(kept)
