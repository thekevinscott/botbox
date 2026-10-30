class LineBuffer:
    """Turns chunks into whole lines, holding only the unterminated rest between chunks."""

    def __init__(self) -> None:
        self.rest: list[bytes] = []

    def add(self, chunk: bytes) -> list[bytes]:
        """The lines `chunk` completes."""
        *lines, rest = chunk.split(b"\n")
        if lines:
            lines[0] = b"".join([*self.rest, lines[0]])
            self.rest = []
        if rest:
            self.rest.append(rest)
        return [line + b"\n" for line in lines]

    def close(self) -> list[bytes]:
        """The unterminated rest, if any."""
        rest, self.rest = b"".join(self.rest), []
        return [rest] if rest else []
