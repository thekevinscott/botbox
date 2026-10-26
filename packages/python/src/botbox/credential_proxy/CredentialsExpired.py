from datetime import datetime
from pathlib import Path


class CredentialsExpired(Exception):
    """The host's login had expired before the run started. botbox never refreshes it."""

    def __init__(self, path: Path, expired: datetime) -> None:
        self.path = path
        self.expired = expired
        super().__init__(
            f"the login in {path} expired at {expired.isoformat()}: use the CLI on the host"
            " to refresh it, then run again"
        )
