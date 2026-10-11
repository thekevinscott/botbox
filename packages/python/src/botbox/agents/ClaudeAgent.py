import shutil
from pathlib import Path

CREDENTIALS = ".credentials.json"


class ClaudeAgent:
    """Claude Code."""

    image = "botbox-claude:latest"
    dockerfile = Path(__file__).with_name("claude.Dockerfile")
    home = "/home/node"
    transcripts = ".claude/projects/**/*.jsonl"
    allow: tuple[str, ...] = ("api.anthropic.com",)

    def __init__(self, *, host_home: Path | None = None) -> None:
        self.host_home = Path.home() / ".claude" if host_home is None else host_home

    def stage_auth(self, home: Path) -> None:
        destination = home / ".claude"
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.host_home / CREDENTIALS, destination / CREDENTIALS)
