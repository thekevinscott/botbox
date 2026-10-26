import asyncio
from contextlib import suppress

from adocker import Container
from botbox.remove_within import remove_within
from botbox.warned import warned


async def stop_proxy(proxy: Container, stdin: asyncio.StreamWriter, grace: float) -> None:
    """End `proxy` by closing its `stdin`, then remove it.

    Its attached client is killed if it outlives `grace`. Removing the container then stops it
    if it is still running; that gets `REMOVE_SECONDS`.
    """
    stdin.close()
    with suppress(Exception):
        async with asyncio.timeout(grace):
            await proxy.wait()
    await warned(remove_within(proxy.name), f"remove its proxy {proxy.name}")
