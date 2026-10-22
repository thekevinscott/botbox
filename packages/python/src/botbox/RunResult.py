from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RunResult:
    """What a run left behind. Nothing parsed.

    From a session, `stdout` keeps only the lines that weren't events, the last 1 MiB of them.
    `exit_code` is -1 when no exit code came back, including an interrupted session.
    `transcript` maps each transcript file's path, relative to the agent's home, to its text.
    `proxy` is the proxy's log: every connection, admitted or refused.
    `image` is the tag that ran: the layered tag when a `dockerfile` was given, else the agent's.
    """

    stdout: str
    stderr: str
    exit_code: int
    transcript: dict[str, str]
    proxy: str
    image: str
