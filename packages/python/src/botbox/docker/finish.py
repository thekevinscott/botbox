import asyncio
from collections.abc import Iterable
from typing import Any


async def finish(
    process: asyncio.subprocess.Process, readers: Iterable[asyncio.Future[Any]]
) -> None:
    """Stop the readers of `process`'s pipes and close them, once its group is reaped or given up.

    A child that left the group can hold the pipes open forever.
    """
    readers = list(readers)
    for reader in readers:
        reader.cancel()
    process._transport.close()  # type: ignore[attr-defined]
    await asyncio.gather(*readers, return_exceptions=True)
