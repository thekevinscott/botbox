from pathlib import Path


class CredentialProxy:
    """A running credential proxy: its container and the socket it serves."""

    def __init__(self, name: str, socket: Path) -> None:
        self.name = name
        self.socket = socket
