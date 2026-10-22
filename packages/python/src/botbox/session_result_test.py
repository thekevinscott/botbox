import asyncio
from pathlib import Path
from unittest.mock import Mock

from botbox.docker.Capture import Capture
from botbox.Session import Session
from botbox.session_result import session_result


async def it_reads_transcripts_and_retains_partial_output(tmp_path: Path) -> None:
    (tmp_path / "turn.jsonl").write_text("partial transcript\n")
    live = Session(
        Mock(transcripts="*.jsonl"),
        Mock(),
        Capture(bytearray(b"partial\xff")),
        bytearray(b"error\xff"),
        asyncio.get_running_loop().create_future(),
    )
    await session_result(live, tmp_path, "proxy log", "image", -1)
    assert live.result is not None
    assert live.result.transcript == {"turn.jsonl": "partial transcript\n"}
    assert live.result.stdout == "partial�"
    assert live.result.stderr == "error�"
    assert live.result.proxy == "proxy log"
    assert live.result.exit_code == -1
