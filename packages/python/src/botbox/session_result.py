import asyncio
from functools import partial
from pathlib import Path

from botbox.capture_result import capture_result
from botbox.RunResult import RunResult
from botbox.Session import Session


async def session_result(
    live: Session,
    home: Path,
    proxy: Path,
    image: str,
    exit_code: int,
) -> None:
    """Capture a stopped session before its temporary home is removed."""
    live.result = await asyncio.to_thread(
        capture_result,
        partial(
            RunResult,
            live.stdout.into.decode(errors="replace"),
            live.stderr.decode(errors="replace"),
            exit_code,
            image,
        ),
        home,
        live.agent.transcripts,
        proxy,
    )
