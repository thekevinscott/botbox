from botbox.docker.run_docker import run_docker


async def create_volume(name: str, label: str) -> None:
    """Create the named volume `name` with `label`."""
    await run_docker("volume", "create", "--label", label, name)


async def remove_volume(name: str) -> None:
    """Remove the volume `name`. Raises DockerException if a container still uses it."""
    await run_docker("volume", "rm", "--force", name)
