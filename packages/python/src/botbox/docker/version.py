import json
from typing import Any

from botbox.docker.run_docker import run_docker


async def version() -> dict[str, Any]:
    """The client's and daemon's versions. Raises DockerException if the daemon is unreachable."""
    result: dict[str, Any] = json.loads(await run_docker("version", "--format", "json"))
    return result
