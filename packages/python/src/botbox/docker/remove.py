from botbox.docker.run_docker import run_docker


async def remove(container: str) -> None:
    """Remove `container`, running or not."""
    await run_docker("rm", "--force", container)
