from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from botbox.session_result import session_result


@pytest.fixture(autouse=True)
def capture() -> Iterator[Mock]:
    with patch("botbox.session_result.capture_result", autospec=True) as m:
        yield m


def describe_session_result() -> None:
    async def it_captures_partial_output_with_the_agents_transcripts(capture: Mock) -> None:
        live = Mock(
            agent=Mock(transcripts="*.jsonl"),
            stdout=Mock(into=bytearray(b"partial\xff")),
            stderr=bytearray(b"error\xff"),
        )
        await session_result(live, Path("/home"), Path("/proxy.log"), "image", -1)
        [make, home, pattern, log] = capture.call_args.args
        assert (home, pattern, log) == (Path("/home"), "*.jsonl", Path("/proxy.log"))
        made = make(Path("/files"))
        assert (made.stdout, made.stderr, made.exit_code, made.image, made.files) == (
            "partial�",
            "error�",
            -1,
            "image",
            Path("/files"),
        )
        assert live.result is capture.return_value
