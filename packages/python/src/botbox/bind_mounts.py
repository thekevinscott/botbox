import posixpath
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

Mount = tuple[str | Path, str | Path, Literal["ro", "rw"]]


def bind_mounts(
    mounts: Sequence[Mount], *, workdir: str | Path | None, home: str
) -> list[tuple[str, str, str]]:
    """Check `mounts` and `workdir` and return the mounts as docker volumes.

    A missing host path is created as a dir owned by the caller: Docker would create it,
    root-owned. A `workdir` outside every mount, the agent's home included, raises, and
    nothing is created.
    """
    volumes: list[tuple[str, str, str]] = [
        (str(Path(host).resolve()), Path(container).as_posix(), mode)
        for host, container, mode in mounts
    ]
    if workdir is not None:
        start = posixpath.normpath(Path(workdir).as_posix())
        targets = [home, *(posixpath.normpath(target) for _, target, _ in volumes)]
        if not any(start == t or start.startswith(t.rstrip("/") + "/") for t in targets):
            raise ValueError(f"workdir {workdir} is not a mounted path or inside one")
    for source, _, _ in volumes:
        if not Path(source).exists():
            Path(source).mkdir(parents=True)
    return volumes
