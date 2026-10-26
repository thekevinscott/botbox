import asyncio

from adocker.run_docker import run_docker


async def remove_volume(name: str, seconds: float) -> None:
    """Force-remove volume `name`, raising TimeoutError if the daemon takes over `seconds`."""
    try:
        async with asyncio.timeout(seconds):
            await run_docker("volume", "rm", "--force", name)
    except TimeoutError:
        raise TimeoutError(f"the daemon did not remove it within {seconds:g}s") from None
