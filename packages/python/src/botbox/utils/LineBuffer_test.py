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

    def describe_a_limit() -> None:
        def it_passes_on_a_rest_that_reaches_it_unterminated() -> None:
            buffer = LineBuffer(limit=4)
            assert buffer.add(b"ab") == []
            assert buffer.add(b"cd") == [b"abcd"]
            assert buffer.add(b"e\n") == [b"e\n"]

        def it_passes_on_a_rest_that_jumps_past_it() -> None:
            buffer = LineBuffer(limit=4)
            assert buffer.add(b"abc") == []
            assert buffer.add(b"de") == [b"abcde"]

        def it_counts_only_the_rest_after_a_newline() -> None:
            buffer = LineBuffer(limit=4)
            assert buffer.add(b"ab\ncde") == [b"ab\n"]
            assert buffer.add(b"f") == [b"cdef"]

        def it_counts_afresh_after_close() -> None:
            buffer = LineBuffer(limit=4)
            buffer.add(b"abc")
            buffer.close()
            assert buffer.add(b"def") == []
            assert buffer.add(b"g") == [b"defg"]

        def it_leaves_whole_lines_whole() -> None:
            assert LineBuffer(limit=4).add(b"abcdefgh\n") == [b"abcdefgh\n"]

        def it_keeps_every_byte_in_order() -> None:
            buffer = LineBuffer(limit=3)
            chunks = [b"ab", b"cd\nef", b"ghij", b"\nk"]
            out = [line for chunk in chunks for line in buffer.add(chunk)] + buffer.close()
            assert b"".join(out) == b"".join(chunks)

        def it_defaults_to_64_mib() -> None:
            assert LineBuffer().limit == 64 << 20
