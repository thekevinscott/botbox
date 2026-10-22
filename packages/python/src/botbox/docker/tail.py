import asyncio


async def tail(stream: asyncio.StreamReader, limit: int) -> bytes:
    """Read `stream` to its end and return its last `limit` bytes."""
    kept = b""
    while chunk := await stream.read(limit):
        kept = (kept + chunk)[-limit:]
    return kept
