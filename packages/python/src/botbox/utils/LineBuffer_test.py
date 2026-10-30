from botbox.utils.LineBuffer import LineBuffer


def describe_LineBuffer() -> None:
    def it_yields_each_whole_line() -> None:
        buffer = LineBuffer()
        buffer += b"one\ntwo\n"
        assert list(buffer) == [b"one\n", b"two\n"]

    def it_joins_a_line_split_across_chunks() -> None:
        buffer = LineBuffer()
        for chunk in (b"o", b"n", b"e\ntw", b"o\n"):
            buffer += chunk
        assert list(buffer) == [b"one\n", b"two\n"]

    def it_holds_a_line_until_its_newline() -> None:
        buffer = LineBuffer()
        buffer += b'{"foo": "bar"'
        assert list(buffer) == []
        buffer += b"}\n{"
        assert list(buffer) == [b'{"foo": "bar"}\n']

    def it_yields_each_line_once() -> None:
        buffer = LineBuffer()
        buffer += b"one\n"
        assert list(buffer) == [b"one\n"]
        buffer += b"two\n"
        assert list(buffer) == [b"two\n"]

    def it_keeps_lines_an_iteration_left_behind() -> None:
        buffer = LineBuffer()
        buffer += b"one\ntwo\n"
        assert next(iter(buffer)) == b"one\n"
        assert list(buffer) == [b"two\n"]

    def it_yields_empty_lines() -> None:
        buffer = LineBuffer()
        buffer += b"\n\n"
        assert list(buffer) == [b"\n", b"\n"]

    def it_yields_the_unterminated_rest_last_once_closed() -> None:
        buffer = LineBuffer()
        buffer += b"one\npa"
        buffer += b"rt"
        buffer.close()
        buffer.close()
        assert list(buffer) == [b"one\n", b"part"]

    def it_yields_nothing_more_on_close_after_a_newline() -> None:
        buffer = LineBuffer()
        buffer += b"one\n"
        buffer.close()
        assert list(buffer) == [b"one\n"]

    def it_yields_a_line_far_longer_than_a_chunk() -> None:
        buffer = LineBuffer()
        for _ in range(256):
            buffer += b"x" * 65536
        buffer += b"\n"
        assert list(buffer) == [b"x" * 65536 * 256 + b"\n"]
