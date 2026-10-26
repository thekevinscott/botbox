from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class Agent(Protocol):
    """What botbox needs to know to run an agent's CLI in a container."""

    image: str
    dockerfile: Path
    home: str
    """Home directory in the container; the run's home volume is mounted here."""
    sessions_dir: str
    """Directory, relative to `home`, the CLI writes its `.jsonl` session transcripts under."""
    allow: tuple[str, ...]
    """Hosts the CLI needs the proxy to admit."""

    def stage_auth(self, home: Path) -> None:
        """Copy the host's credentials into `home`, staged for the run's home volume."""
        ...

    def command(self, prompt: str) -> str:
        """The agent's CLI invocation for `prompt`, as a shell string for `run()`."""
        ...


@runtime_checkable
class SessionAgent(Agent, Protocol):
    """An agent whose CLI can hold a live session: messages in on stdin, events out on stdout."""

    def session_command(self) -> str:
        """The CLI invocation that reads messages from stdin until stdin closes."""
        ...

    def encode(self, message: str) -> str:
        """`message` as one line for the CLI's stdin, without the trailing newline."""
        ...

    def turn_ended(self, event: dict[str, Any]) -> bool:
        """Whether `event`, one line of the CLI's stdout, is the last of a turn."""
        ...
