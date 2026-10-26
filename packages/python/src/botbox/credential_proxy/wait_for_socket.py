import asyncio
import os
import time
from pathlib import Path

POLL = 0.05
ERROR_BYTES = 64 * 1024


async def wait_for_socket(
    socket: Path, client: asyncio.Future[int], log: Path, timeout: float
) -> None:
    """Return once `socket` accepts a connection, which can come a moment after it exists.

    Raise with the end of `log` if `client` exits or `timeout` passes first.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            _, writer = await asyncio.open_unix_connection(socket)
        except OSError:
            pass
        else:
            writer.close()
            await writer.wait_closed()
            return
        if client.done() or time.monotonic() > deadline:
            with log.open("rb") as output:
                output.seek(max(0, output.seek(0, os.SEEK_END) - ERROR_BYTES))
                text = output.read().decode(errors="replace")
            cause = client.exception() if client.done() else None
            raise RuntimeError(f"botbox credential proxy did not start:\n{text}") from cause
        await asyncio.sleep(POLL)
