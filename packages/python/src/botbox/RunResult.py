from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RunResult:
    """What a run left behind. Nothing parsed.

    `exit_code` is -1 when no exit code came back: the Docker daemon went away mid-run.
    `transcript` maps each transcript file's path, relative to the agent's home, to its text.
    `proxy` is the proxy's log: every connection, admitted or refused.
    `container` is the id of the exited container, left in place until the caller removes it or
    the box's `with` block exits.
    `image` is the tag that ran: the layered tag when a `dockerfile` was given, else the agent's.
    """

    stdout: str
    stderr: str
    exit_code: int
    transcript: dict[str, str]
    proxy: str
    container: str
    image: str
