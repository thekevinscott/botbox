from pathlib import Path
from typing import Protocol


class Agent(Protocol):
    """What botbox needs to know to run an agent's CLI in a container."""

    image: str
    dockerfile: Path
    home: str
    """Home directory in the container; the per-run temp home is mounted here."""
    transcripts: str
    """Glob, relative to `home`, matching the files the CLI writes its transcript to."""
    allow: tuple[str, ...]
    """Hosts the CLI needs the proxy to admit."""

    def stage_auth(self, home: Path) -> None:
        """Copy the host's credentials into `home`, the per-run temp home."""
        ...
