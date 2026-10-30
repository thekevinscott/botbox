LIMIT = 64 << 20


class LineBuffer:
    """Turns chunks into whole lines, holding only the unterminated rest between chunks.

    A rest that reaches `limit` bytes comes out as it is, unterminated, so memory stays bounded;
    the bytes are unchanged, but that line arrives in pieces.
    """

    def __init__(self, limit: int = LIMIT) -> None:
        self.limit = limit
        self.rest: list[bytes] = []
        self.held = 0

    def add(self, chunk: bytes) -> list[bytes]:
        """The lines `chunk` completes."""
        *lines, rest = chunk.split(b"\n")
        if lines:
            lines[0] = b"".join([*self.rest, lines[0]])
            self.rest, self.held = [], 0
        added = [line + b"\n" for line in lines]
        if rest:
            self.rest.append(rest)
            self.held += len(rest)
            if self.held >= self.limit:
                added += self.close()
        return added

    def close(self) -> list[bytes]:
        """The unterminated rest, if any."""
        rest = b"".join(self.rest)
        self.rest, self.held = [], 0
        return [rest] if rest else []
