from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RunResult:
    """What a run left behind. Nothing parsed.

    `exit_code` is -1 when no exit code came back, including an interrupted session.
    `transcript` maps each transcript file's path, relative to the agent's home, to its text.
    `proxy` is the proxy's log: every connection, admitted or refused.
    `image` is the tag that ran: the layered tag when a `dockerfile` was given, else the agent's.
    `truncated` is set when `stdout` or `stderr` passed its cap and only its end was kept.
    """

    stdout: str
    stderr: str
    exit_code: int
    transcript: dict[str, str]
    proxy: str
    image: str
    truncated: bool = False
