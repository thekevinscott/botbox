from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Limits:
    """Caps on the agent's container.

    `memory` is a `docker run --memory` size and `pids` a `--pids-limit`; `None`, the default,
    is no cap.
    """

    memory: str | None = None
    pids: int | None = None

    def args(self) -> list[str]:
        return [
            *([] if self.memory is None else ["--memory", self.memory]),
            *([] if self.pids is None else ["--pids-limit", str(self.pids)]),
        ]
