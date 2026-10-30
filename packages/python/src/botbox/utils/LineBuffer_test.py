from botbox.utils.LineBuffer import LineBuffer


def describe_LineBuffer() -> None:
    def it_returns_each_whole_line() -> None:
        assert LineBuffer().add(b"one\ntwo\n") == [b"one\n", b"two\n"]

    def it_joins_a_line_split_across_chunks() -> None:
        buffer = LineBuffer()
        added = [buffer.add(chunk) for chunk in (b"o", b"n", b"e\ntw", b"o\n")]
        assert added == [[], [], [b"one\n"], [b"two\n"]]

    def it_holds_a_line_until_its_newline() -> None:
        buffer = LineBuffer()
        assert buffer.add(b'{"foo": "bar"') == []
        assert buffer.add(b"}\n{") == [b'{"foo": "bar"}\n']

    def it_returns_empty_lines() -> None:
        assert LineBuffer().add(b"\n\n") == [b"\n", b"\n"]

    def it_returns_the_unterminated_rest_on_close() -> None:
        buffer = LineBuffer()
        buffer.add(b"one\npa")
        buffer.add(b"rt")
        assert buffer.close() == [b"part"]
        assert buffer.close() == []

    def it_returns_nothing_on_close_after_a_newline() -> None:
        buffer = LineBuffer()
        buffer.add(b"one\n")
        assert buffer.close() == []

    def it_returns_a_line_far_longer_than_a_chunk() -> None:
        buffer = LineBuffer()
        for _ in range(256):
            assert buffer.add(b"x" * 65536) == []
        assert buffer.add(b"\n") == [b"x" * 65536 * 256 + b"\n"]
