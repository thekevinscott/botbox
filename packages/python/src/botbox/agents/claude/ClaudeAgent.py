import json
import shlex
import shutil
from pathlib import Path

CREDENTIALS = ".credentials.json"
API_KEY = "api_key"


class ClaudeAgent:
    """Claude Code."""

    image = "botbox-claude:latest"
    dockerfile = Path(__file__).with_name("Dockerfile")
    home = "/home/user"
    transcripts = ".claude/projects/**/*.jsonl"
    allow: tuple[str, ...] = ("api.anthropic.com",)

    def __init__(
        self,
        model: str | None = None,
        effort: str | None = None,
        *,
        api_key: str | None = None,
        host_home: Path | None = None,
    ) -> None:
        self.model = model
        self.effort = effort
        self.api_key = api_key
        self.host_home = Path.home() / ".claude" if host_home is None else host_home

    def command(self, prompt: str) -> str:
        command = (
            f"claude -p {shlex.quote(prompt)} --output-format json --dangerously-skip-permissions"
            " --strict-mcp-config"
        )
        if self.model is not None:
            command += f" --model {self.model}"
        if self.effort is not None:
            command += f" --effort {self.effort}"
        return command

    def stage_auth(self, home: Path) -> None:
        destination = home / ".claude"
        destination.mkdir()
        if self.api_key is None:
            shutil.copy(self.host_home / CREDENTIALS, destination / CREDENTIALS)
            return
        key = destination / API_KEY
        key.touch(mode=0o600)
        key.write_text(self.api_key)
        helper = f"cat {self.home}/.claude/{API_KEY}"
        (destination / "settings.json").write_text(json.dumps({"apiKeyHelper": helper}))
