import json
from typing import Any

from adocker.run_docker import run_docker


class Daemon:
    """The Docker daemon the `docker` CLI reaches."""

    async def version(self) -> dict[str, Any]:
        """The client's and daemon's versions. Raises DockerException if it is unreachable."""
        result: dict[str, Any] = json.loads(await run_docker("version", "--format", "json"))
        return result
