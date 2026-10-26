from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RunResult:
    """What a run left behind. Nothing parsed.

    `exit_code` is -1 when no exit code came back, including an interrupted session.
    `proxy` is the proxy's log: every connection, admitted or refused.
    `image` is the tag that ran: the layered tag when a `dockerfile` was given, else the agent's.
    """

    stdout: str
    stderr: str
    exit_code: int
    proxy: str
    image: str
