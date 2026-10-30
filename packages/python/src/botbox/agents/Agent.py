from abc import ABC, abstractmethod
from pathlib import Path

from botbox.agents.HomeFiles import HomeFiles
from botbox.credential_proxy import CredentialSource


class Agent(ABC):
    """What botbox needs to know to run an agent's CLI in a container.

    Subclass it and implement `stage_auth` and `command`.
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
