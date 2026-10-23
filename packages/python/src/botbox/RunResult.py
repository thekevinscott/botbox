from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RunResult:
    """The exit code; -1 when no exit code came back, including an interrupted session."""

    exit_code: int
