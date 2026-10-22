import asyncio
import warnings
from typing import Any

from botbox.docker.reap import reap
from botbox.docker.settle import settle


async def stop(process: asyncio.subprocess.Process, *drains: asyncio.Future[Any]) -> None:
    """Reap `process`'s group through any cancels. A group that won't stop is a warning."""
    try:
        await settle(reap(process, *drains))
    except Exception as error:
        warnings.warn(
            f"docker's process group {process.pid} did not stop: {error!r}",
            RuntimeWarning,
            stacklevel=2,
        )
