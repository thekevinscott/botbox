from adocker.run_docker import run_docker


async def stop(container: str, seconds: int) -> None:
    """Stop `container`, killing it if it is still up after `seconds`."""
    await run_docker("stop", "--time", str(seconds), container)
