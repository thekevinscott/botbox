from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from botbox.agents.HomeFiles import HomeFiles
from botbox.credential_proxy import CredentialSource

NO_SESSION = "NOT IMPLEMENTED: {name} has no session mode."


class Agent(ABC):
    """What botbox needs to know to run an agent's CLI in a container.

    Subclass it and implement `stage_auth` and `command`. An agent whose CLI can hold a live
    session, messages in on stdin and events out on stdout, also overrides `session_command`,
    `encode` and `turn_ended`.
    """

    image: str
    dockerfile: Path
    home: str
    """Home directory in the container. The image creates it, writable by any uid."""
    sessions_dir: str
    """Directory, relative to `home`, the CLI writes its `.jsonl` session transcripts under."""
    allow: tuple[str, ...]
    """Hosts the CLI needs the proxy to admit."""
    credential_source: CredentialSource | None = None
    """The host credential the proxy sends upstream, so the box never holds it, or None to have
    `stage_auth` copy the login in."""

    @abstractmethod
    def stage_auth(self, home: HomeFiles) -> None:
        """Stage the agent's login into `home`, written into the container's home at start: a
        copy of the host's, or a placeholder when the credential proxy sends the real one."""

    @abstractmethod
    def command(self, prompt: str) -> str:
        """The agent's CLI invocation for `prompt`, as a shell string for `run()`."""

    def session_command(self) -> str:
        """The CLI invocation that reads messages from stdin until stdin closes."""
        raise NotImplementedError(NO_SESSION.format(name=type(self).__name__))

    def encode(self, message: str) -> str:
        """`message` as one line for the CLI's stdin, without the trailing newline."""
        raise NotImplementedError(NO_SESSION.format(name=type(self).__name__))

    def turn_ended(self, event: dict[str, Any]) -> bool:
        """Whether `event`, one line of the CLI's stdout, is the last of a turn."""
        raise NotImplementedError(NO_SESSION.format(name=type(self).__name__))

    def filter_stdout(self, line: bytes) -> bytes | None:
        """The bytes to write for `line`, one line of the CLI's stdout, or None to drop it.

        `line` keeps its trailing newline, except the unterminated rest the CLI leaves at exit.
        What is returned is written as is, so keep the newline. An error raised here ends the
        run or session with that error. The default writes every line unchanged.
        """
        return line
