from unittest.mock import Mock

import pytest

from botbox.utils.Lines import Lines


@pytest.fixture
def sink() -> Mock:
    return Mock()


def passed(sink: Mock) -> list[bytes]:
    return [c.args[0] for c in sink.call_args_list]


def describe_Lines() -> None:
    def it_passes_each_whole_line(sink: Mock) -> None:
        Lines(sink)(b"one\ntwo\n")
        assert passed(sink) == [b"one\n", b"two\n"]

    def it_joins_a_line_split_across_chunks(sink: Mock) -> None:
        lines = Lines(sink)
        for chunk in (b"o", b"n", b"e\ntw", b"o\n"):
            lines(chunk)
        assert passed(sink) == [b"one\n", b"two\n"]

    def it_holds_a_line_until_its_newline(sink: Mock) -> None:
        Lines(sink)(b"one\npart")
        assert passed(sink) == [b"one\n"]

    def it_passes_empty_lines(sink: Mock) -> None:
        Lines(sink)(b"\n\n")
        assert passed(sink) == [b"\n", b"\n"]

    def it_passes_the_unterminated_rest_on_close(sink: Mock) -> None:
        lines = Lines(sink)
        lines(b"pa")
        lines(b"rt")
        lines.close()
        lines.close()
        assert passed(sink) == [b"part"]

    def it_passes_nothing_on_close_after_a_newline(sink: Mock) -> None:
        lines = Lines(sink)
        lines(b"one\n")
        lines.close()
        assert passed(sink) == [b"one\n"]

    def it_passes_a_line_far_longer_than_a_chunk(sink: Mock) -> None:
        lines = Lines(sink)
        for _ in range(256):
            lines(b"x" * 65536)
        lines(b"\n")
        assert passed(sink) == [b"x" * 65536 * 256 + b"\n"]
