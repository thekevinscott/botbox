from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from botbox.credential_proxy import CredentialSource


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
        """Stage the agent's login into `home`, a host temp directory copied into the run's home:
        a copy of the host's, or a placeholder when the credential proxy sends the real one."""
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


@runtime_checkable
class InjectingAgent(Agent, Protocol):
    """An agent whose credential the proxy sends upstream, so the box never holds it.

    An agent without `credential_source` has its credentials copied in by `stage_auth`.
    """

    @property
    def credential_source(self) -> CredentialSource | None:
        """The host credential the proxy injects, or None to have `stage_auth` copy it."""
        ...
