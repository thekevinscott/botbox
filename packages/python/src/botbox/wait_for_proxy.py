import asyncio
import time
from contextlib import suppress
from pathlib import Path

POLL = 0.05
ERROR_BYTES = 64 * 1024


async def wait_for_proxy(
    socket: Path, client: asyncio.Future[int], output: Path, timeout: float
) -> None:
    """Return once `socket` exists. Raise with the end of `output` if `client` exits or
    `timeout` passes."""
    deadline = time.monotonic() + timeout
    while not socket.exists():
        if client.done() or time.monotonic() > deadline:
            cause = client.exception() if client.done() else None
            text = ""
            with suppress(OSError), output.open("rb") as log:
                log.seek(max(0, log.seek(0, 2) - ERROR_BYTES))
                text = log.read().decode(errors="replace")
            raise RuntimeError(f"botbox proxy did not start:\n{text}") from cause
        await asyncio.sleep(POLL)
