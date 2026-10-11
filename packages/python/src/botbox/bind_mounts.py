import posixpath
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

Mount = tuple[str | Path, str | Path, Literal["ro", "rw"]]


def bind_mounts(
    mounts: Sequence[Mount], *, workdir: str | Path | None, home: str
) -> list[tuple[str, str, str]]:
    """Check `mounts` and `workdir` and return the mounts as docker volumes.

    A missing host path raises: Docker would create it, root-owned. So would a `workdir`
    outside every mount, the agent's home included, so that raises too.
    """
    volumes: list[tuple[str, str, str]] = []
    for host, container, mode in mounts:
        source = Path(host).resolve()
        if not source.exists():
            raise FileNotFoundError(f"mount source {host} does not exist")
        volumes.append((str(source), Path(container).as_posix(), mode))
    if workdir is not None:
        start = posixpath.normpath(Path(workdir).as_posix())
        targets = [home, *(posixpath.normpath(target) for _, target, _ in volumes)]
        if not any(start == t or start.startswith(t.rstrip("/") + "/") for t in targets):
            raise ValueError(f"workdir {workdir} is not a mounted path or inside one")
    return volumes
