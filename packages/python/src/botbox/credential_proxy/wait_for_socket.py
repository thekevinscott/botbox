import asyncio
import os
import time
from pathlib import Path

from adocker import Container, DockerException

POLL = 0.05
ERROR_BYTES = 64 * 1024


async def wait_for_socket(
    through: Container, socket: str, client: asyncio.Future[int], log: Path, timeout: float
) -> None:
    """Return once `socket` accepts a connection from inside `through`, which needs socat.

    The socket sits in a volume the host can't see, and accepts a moment after it exists.
    Raise with the end of `log` if `client` exits or `timeout` passes first.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            await through.exec("socat", "-u", "OPEN:/dev/null", f"UNIX-CONNECT:{socket}")
        except DockerException:
            pass
        else:
            return
        if client.done() or time.monotonic() > deadline:
            with log.open("rb") as output:
                output.seek(max(0, output.seek(0, os.SEEK_END) - ERROR_BYTES))
                text = output.read().decode(errors="replace")
            cause = client.exception() if client.done() else None
            raise RuntimeError(f"botbox credential proxy did not start:\n{text}") from cause
        await asyncio.sleep(POLL)
