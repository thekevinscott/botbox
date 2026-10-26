from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Mount:
    """`source` mounted at `target` in a container: a host path to bind, or a volume's name.

    `subpath`, for a volume only, mounts that directory inside the volume instead of its root.
    """

    kind: Literal["bind", "volume"]
    source: str
    target: str
    read_only: bool = False
    subpath: str | None = None

    def __post_init__(self) -> None:
        if self.subpath is not None and self.kind != "volume":
            raise ValueError("only a volume mount takes a subpath")

    @property
    def volume_flag(self) -> str:
        """The mount as `docker run --volume` takes it, which has no subpath."""
        return f"{self.source}:{self.target}:{'ro' if self.read_only else 'rw'}"

    @property
    def flag(self) -> tuple[str, str]:
        """The `docker run` flag and value for the mount: `--volume`, or `--mount` with a subpath.

        `--volume` creates a missing bind source; `--mount` would refuse it.
        """
        if self.subpath is None:
            return ("--volume", self.volume_flag)
        options = f"type=volume,source={self.source},target={self.target}"
        options += f",volume-subpath={self.subpath}"
        return ("--mount", options + (",readonly" if self.read_only else ""))
