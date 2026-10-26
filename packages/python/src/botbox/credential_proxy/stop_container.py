import asyncio
import warnings

from botbox.docker.remove import remove
from botbox.docker.run_docker import run_docker

STOP_SECONDS = 5
REMOVE_SECONDS = 30


async def stop_container(client: asyncio.Future[int], name: str) -> None:
    """Stop the container so Envoy flushes its access log, then remove it.

    The attached client is killed if it outlives the stop.
    """
    try:
        async with asyncio.timeout(REMOVE_SECONDS):
            await run_docker("stop", "--time", str(STOP_SECONDS), name)
            await asyncio.wait({client}, timeout=STOP_SECONDS)
            client.cancel()
            await asyncio.gather(client, return_exceptions=True)
            await remove(name)
    except Exception as error:
        warnings.warn(
            f"botbox could not remove its credential proxy {name}: {error}",
            RuntimeWarning,
            stacklevel=2,
        )
