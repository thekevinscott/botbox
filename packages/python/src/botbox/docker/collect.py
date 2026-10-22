import asyncio

CHUNK = 64 * 1024


async def collect(stream: asyncio.StreamReader, into: bytearray, limit: int | None = None) -> None:
    """Read `stream` to its end into `into`, keeping only its last `limit` bytes if given.

    `into` belongs to the caller, so what was read survives this being cancelled.
    """
    while chunk := await stream.read(CHUNK):
        into += chunk
        if limit is not None:
            del into[: max(len(into) - limit, 0)]
