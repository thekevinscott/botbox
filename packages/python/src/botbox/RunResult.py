from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RunResult:
    """How a run ended. What it wrote is kept only under `output`.

    `exit_code` is -1 when no exit code came back, including an interrupted session.
    `oom_killed` is Docker's record of whether the kernel killed a process in the agent container,
    the agent or one of its children, for running out of memory. None when no record was read, as
    after a timeout or an interrupted session.
    """

    exit_code: int
    oom_killed: bool | None = None
