from pathlib import Path
from typing import Protocol

from botbox.agents.HomeFiles import HomeFiles


class Agent(Protocol):
    """What botbox needs to know to run an agent's CLI in a container."""

    image: str
    dockerfile: Path
    home: str
    """Home directory in the container. The image creates it, writable by any uid."""
    sessions_dir: str
    """Directory, relative to `home`, the CLI writes its `.jsonl` session transcripts under."""
    allow: tuple[str, ...]
    """Hosts the CLI needs the proxy to admit."""

    def stage_auth(self, home: HomeFiles) -> None:
        """Stage the agent's login into `home`, written into the container's home at start: a
        copy of the host's, or a placeholder when the credential proxy sends the real one."""
        ...

    def command(self, prompt: str) -> str:
        """The agent's CLI invocation for `prompt`, as a shell string for `run()`."""
        ...
