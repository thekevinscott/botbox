from botbox.RunResult import RunResult
from botbox.Session import Session


async def session_result(
    live: Session,
    proxy: str,
    image: str,
    exit_code: int,
) -> None:
    """Capture a stopped session before its temporary home is removed."""
    live.result = RunResult(
        "" if live.stdout is None else live.stdout.into.decode(errors="replace"),
        live.stderr.decode(errors="replace"),
        exit_code,
        proxy,
        image,
    )
