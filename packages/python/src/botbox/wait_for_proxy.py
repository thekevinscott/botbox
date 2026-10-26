import asyncio
import time
from contextlib import suppress
from pathlib import Path

POLL = 0.05
ERROR_BYTES = 64 * 1024
# botbox-proxy prints this once its socket exists, which sits in a volume the host can't see.
READY = b"botbox-proxy: listening\n"


async def wait_for_proxy(client: asyncio.Future[int], output: Path, timeout: float) -> None:
    """Return once the proxy says in `output` that it is listening. Raise with the end of
    `output` if `client` exits or `timeout` passes."""
    deadline = time.monotonic() + timeout
    while True:
        with suppress(OSError):
            if READY in output.read_bytes():
                return
        if client.done() or time.monotonic() > deadline:
            cause = client.exception() if client.done() else None
            text = ""
            with suppress(OSError), output.open("rb") as log:
                log.seek(max(0, log.seek(0, 2) - ERROR_BYTES))
                text = log.read().decode(errors="replace")
            raise RuntimeError(f"botbox proxy did not start:\n{text}") from cause
        await asyncio.sleep(POLL)
