from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Mount:
    """`source` mounted at `target` in a container: a host path to bind, or a volume's name."""

    kind: Literal["bind", "volume"]
    source: str
    target: str
    read_only: bool = False

    @property
    def volume_flag(self) -> str:
        """The mount as `docker run --volume` takes it."""
        return f"{self.source}:{self.target}:{'ro' if self.read_only else 'rw'}"
