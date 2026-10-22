import asyncio


def harvest(drain: asyncio.Future[bytes]) -> bytes:
    """What `drain` read, or nothing if it didn't finish, which it is then stopped from doing."""
    if not drain.done():
        drain.cancel()
        return b""
    if drain.cancelled() or drain.exception():
        return b""
    return drain.result()
