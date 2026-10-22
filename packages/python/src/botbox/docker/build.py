from collections.abc import Mapping
from pathlib import Path

from botbox.docker.run_docker import run_docker


async def build(
    context: Path, *, tag: str, file: Path, contexts: Mapping[str, str | Path] | None = None
) -> None:
    """Build `file` in `context` with buildx and load it as `tag`."""
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
        str(file),
        *named,
        str(context),
    )
