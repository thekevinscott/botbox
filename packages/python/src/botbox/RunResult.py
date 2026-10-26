from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RunResult:
    """How a run ended. What it wrote is kept only under `output`.

    `exit_code` is -1 when no exit code came back, including an interrupted session.
    """

    exit_code: int
