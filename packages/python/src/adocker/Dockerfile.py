from collections.abc import Mapping
from pathlib import Path

from adocker.Image import Image
from adocker.run_docker import run_docker


class Dockerfile:
    """A Dockerfile at `path`, built in `context`, its own folder unless given."""

    def __init__(self, path: str | Path, *, context: str | Path | None = None) -> None:
        self.path = Path(path)
        self.context = self.path.parent if context is None else Path(context)

    async def build(self, tag: str, *, contexts: Mapping[str, str | Path] | None = None) -> Image:
        """Build it with buildx, load it as `tag`, and return that image.

        `contexts` are named build contexts. Raises DockerException if the build fails.
        """
        named = [
            arg
            for name, path in (contexts or {}).items()
            for arg in ("--build-context", f"{name}={path}")
        ]
        await run_docker(
            "buildx",
            "build",
            "--load",
            "--progress=quiet",
            "--tag",
            tag,
            "--file",
            str(self.path),
            *named,
            str(self.context),
        )
        return Image(tag)
