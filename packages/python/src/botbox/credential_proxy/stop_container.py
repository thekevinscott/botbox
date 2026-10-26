import asyncio
import warnings
from contextlib import suppress

from adocker import Container

STOP_SECONDS = 5
REMOVE_SECONDS = 30


async def stop_container(container: Container) -> None:
    """Stop the container so Envoy flushes its access log, then remove it.

    The attached client is killed if it outlives the stop.
    """
    try:
        async with asyncio.timeout(REMOVE_SECONDS):
            await container.stop(STOP_SECONDS)
            with suppress(Exception):
                async with asyncio.timeout(STOP_SECONDS):
                    await container.wait()
            await container.remove()
    except Exception as error:
        warnings.warn(
            f"botbox could not remove its credential proxy {container.name}: {error}",
            RuntimeWarning,
            stacklevel=2,
        )
