from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from botbox.session_result import session_result


@pytest.fixture(autouse=True)
def reader() -> Iterator[Mock]:
    with patch(
        "botbox.session_result.read_transcript",
        return_value={"turn.jsonl": "partial"},
    ) as read:
        yield read


def describe_session_result() -> None:
    async def it_retains_partial_output_and_reads_the_agents_transcripts(reader: Mock) -> None:
        live = Mock(
            agent=Mock(sessions_dir="sessions"),
            stdout=Mock(into=bytearray(b"partial\xff")),
            stderr=bytearray(b"error\xff"),
        )
        await session_result(live, Path("/home"), "proxy log", "image", -1)
        reader.assert_called_once_with(Path("/home"), "sessions")
        assert live.result.transcript == {"turn.jsonl": "partial"}
        assert live.result.stdout == "partial�"
        assert live.result.stderr == "error�"
        assert live.result.proxy == "proxy log"
        assert live.result.exit_code == -1
