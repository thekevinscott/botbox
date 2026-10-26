import json
from typing import Any

from adocker.run_docker import run_docker


async def inspect_image(image: str) -> dict[str, Any]:
    """`image`'s id, tags and config. Raises DockerException if there is no such image."""
    [details] = json.loads(await run_docker("image", "inspect", "--format", "json", image))
    result: dict[str, Any] = details
    return result
