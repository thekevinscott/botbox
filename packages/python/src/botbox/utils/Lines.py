from collections.abc import Callable

type Sink = Callable[[bytes], object]


class Lines:
    """A sink for chunks that passes `sink` each whole line; `close` passes the unterminated
    rest."""

    def __init__(self, sink: Sink) -> None:
        self.sink = sink
        self.rest: list[bytes] = []

    def __call__(self, chunk: bytes) -> None:
        *lines, rest = chunk.split(b"\n")
        if lines:
            lines[0] = b"".join([*self.rest, lines[0]])
            self.rest = []
        for line in lines:
            self.sink(line + b"\n")
        if rest:
            self.rest.append(rest)

    def close(self) -> None:
        if self.rest:
            rest, self.rest = b"".join(self.rest), []
            self.sink(rest)
