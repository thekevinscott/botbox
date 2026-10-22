from botbox.docker.run_docker import run_docker


async def wait(container: str) -> int:
    """Wait for `container` to stop and return its exit code."""
    return int(await run_docker("wait", container))
