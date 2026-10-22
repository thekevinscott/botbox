import asyncio
import time
from pathlib import Path

POLL = 0.05


async def wait_for_proxy(
    socket: Path, client: asyncio.Future[int], output: bytearray, timeout: float
) -> None:
    """Return once `socket` exists. Raise with `output` if `client` exits or `timeout` passes."""
    deadline = time.monotonic() + timeout
    while not socket.exists():
        if client.done() or time.monotonic() > deadline:
            cause = client.exception() if client.done() else None
            text = output.decode(errors="replace")
            raise RuntimeError(f"botbox proxy did not start:\n{text}") from cause
        await asyncio.sleep(POLL)
