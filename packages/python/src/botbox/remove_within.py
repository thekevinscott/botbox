import asyncio

from adocker.remove import remove

REMOVE_SECONDS = 30


async def remove_within(container: str, seconds: float = REMOVE_SECONDS) -> None:
    """Remove `container`, or give up after `seconds` so a daemon that hangs can't stall teardown.

    Giving up cancels the removal, which reaps its client, and raises TimeoutError.
    """
    try:
        async with asyncio.timeout(seconds):
            await remove(container)
    except TimeoutError:
        raise TimeoutError(f"the daemon did not remove it within {seconds:g}s") from None
