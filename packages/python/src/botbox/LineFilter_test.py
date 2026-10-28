import pytest

from botbox.LineFilter import LineFilter


class Filter:
    """Drops lines that start with "drop", raises on "boom" and upper-cases the rest."""

    def __init__(self) -> None:
        self.seen: list[bytes] = []

    def __call__(self, line: bytes) -> bytes | None:
        self.seen.append(line)
        if line.startswith(b"boom"):
            raise ValueError(line)
        return None if line.startswith(b"drop") else line.upper()


@pytest.fixture
def written() -> list[bytes]:
    return []


@pytest.fixture
def keep() -> Filter:
    return Filter()


@pytest.fixture
def lines(keep: Filter, written: list[bytes]) -> LineFilter:
    return LineFilter(written.append, keep)


def feed(lines: LineFilter, *chunks: bytes) -> None:
    for chunk in chunks:
        lines(chunk)
    lines.close()


def describe_LineFilter() -> None:
    def describe_through_a_filter() -> None:
        def it_passes_each_whole_line_with_its_newline(lines: LineFilter, keep: Filter) -> None:
            feed(lines, b"a\nb\n")
            assert keep.seen == [b"a\n", b"b\n"]

        def it_joins_a_line_split_mid_line(lines: LineFilter, keep: Filter) -> None:
            feed(lines, b"on", b"e\ntwo\n")
            assert keep.seen == [b"one\n", b"two\n"]

        def it_splits_many_lines_in_one_chunk(lines: LineFilter, keep: Filter) -> None:
            feed(lines, b"1\n2\n3\n4\n")
            assert keep.seen == [b"1\n", b"2\n", b"3\n", b"4\n"]

        def it_joins_a_line_split_across_many_chunks(lines: LineFilter, keep: Filter) -> None:
            feed(lines, b"a", b"b", b"c", b"d\n")
            assert keep.seen == [b"abcd\n"]

        def it_ends_a_held_line_at_a_newline_that_starts_a_chunk(
            lines: LineFilter, keep: Filter
        ) -> None:
            feed(lines, b"x", b"\ny\n")
            assert keep.seen == [b"x\n", b"y\n"]

        def it_passes_empty_lines(lines: LineFilter, keep: Filter) -> None:
            feed(lines, b"\n\n")
            assert keep.seen == [b"\n", b"\n"]

        def it_passes_a_line_longer_than_any_chunk_whole(lines: LineFilter, keep: Filter) -> None:
            line = b"x" * 150_000 + b"\n"
            feed(lines, *(line[i : i + 65536] for i in range(0, len(line), 65536)))
            assert keep.seen == [line]

        def it_holds_an_unterminated_line_until_closed(
            lines: LineFilter, keep: Filter, written: list[bytes]
        ) -> None:
            lines(b"a\nrest")
            assert keep.seen == [b"a\n"]
            lines.close()
            assert keep.seen == [b"a\n", b"rest"]
            assert written == [b"A\n", b"REST"]

        def it_passes_the_rest_once_however_often_closed(lines: LineFilter, keep: Filter) -> None:
            lines(b"rest")
            lines.close()
            lines.close()
            assert keep.seen == [b"rest"]

        def it_closes_on_leaving_the_block(keep: Filter, written: list[bytes]) -> None:
            with LineFilter(written.append, keep) as lines:
                lines(b"rest")
            assert written == [b"REST"]

        def it_passes_nothing_for_no_output(
            lines: LineFilter, keep: Filter, written: list[bytes]
        ) -> None:
            feed(lines)
            feed(lines, b"")
            assert (keep.seen, written) == ([], [])

        def it_writes_what_the_filter_returns(lines: LineFilter, written: list[bytes]) -> None:
            feed(lines, b"keep\n")
            assert written == [b"KEEP\n"]

        def it_drops_a_line_the_filter_returns_none_for(
            lines: LineFilter, written: list[bytes]
        ) -> None:
            feed(lines, b"one\ndrop me\ntwo\ndrop")
            assert written == [b"ONE\n", b"TWO\n"]

        def it_raises_what_the_filter_raises_and_writes_nothing_for_that_line(
            lines: LineFilter, written: list[bytes]
        ) -> None:
            with pytest.raises(ValueError, match="boom"):
                lines(b"one\nboom\ntwo\n")
            assert written == [b"ONE\n"]

        def it_raises_what_the_filter_raises_for_the_rest_on_close(
            lines: LineFilter, written: list[bytes]
        ) -> None:
            lines(b"one\nboom")
            with pytest.raises(ValueError, match="boom"):
                lines.close()
            assert written == [b"ONE\n"]

        def it_does_not_pass_a_raising_line_again(lines: LineFilter, keep: Filter) -> None:
            lines(b"boom")
            with pytest.raises(ValueError, match="boom"):
                lines.close()
            lines.close()
            assert keep.seen == [b"boom"]
