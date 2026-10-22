import asyncio
from contextlib import suppress
from typing import IO

from botbox.docker.remove import remove
from botbox.warned import warned


async def stop_proxy(
    client: asyncio.Future[int], stdin: IO[bytes], name: str, grace: float
) -> None:
    """End the proxy `name` by closing its `stdin`, then remove it.

    Its attached `client` is cancelled if it outlives `grace`, which kills it. Removing the
    container then stops it if it is still running.
    """
    with suppress(OSError):
        stdin.close()
    await asyncio.wait({client}, timeout=grace)
    client.cancel()
    await asyncio.gather(client, return_exceptions=True)
    await warned(remove(name), f"remove its proxy {name}")
