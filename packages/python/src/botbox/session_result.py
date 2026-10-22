import asyncio
from pathlib import Path

from botbox.read_transcript import read_transcript
from botbox.RunResult import RunResult
from botbox.Session import Session


async def session_result(
    live: Session,
    home: Path,
    proxy: str,
    image: str,
    exit_code: int,
) -> None:
    """Capture a stopped session before its temporary home is removed."""
    transcript = await asyncio.to_thread(read_transcript, home, live.agent.transcripts)
    live.result = RunResult(
        live.output(),
        live.stderr.decode(errors="replace"),
        exit_code,
        transcript,
        proxy,
        image,
    )
