import asyncio

CHUNK = 64 * 1024


async def discard(stream: asyncio.StreamReader) -> None:
    """Read `stream` to its end and keep none of it."""
    while await stream.read(CHUNK):
        pass
