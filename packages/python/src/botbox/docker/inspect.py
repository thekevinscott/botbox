import json
from typing import Any

from botbox.docker.run_docker import run_docker


async def inspect(container: str) -> dict[str, Any]:
    """`container`'s state and config. Raises DockerException if there is no such container."""
    [details] = json.loads(await run_docker("container", "inspect", "--format", "json", container))
    result: dict[str, Any] = details
    return result
