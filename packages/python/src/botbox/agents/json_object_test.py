import pytest

from botbox.agents.json_object import json_object


def describe_json_object() -> None:
    def it_parses_a_json_object() -> None:
        assert json_object(b'{"type": "end"}\n') == {"type": "end"}

    @pytest.mark.parametrize("line", [b"starting\n", b"[1, 2]\n", b"\n", b"\xff\xfe\n", b'{"n":'])
    def it_reads_none_from_anything_else(line: bytes) -> None:
        assert json_object(line) is None
