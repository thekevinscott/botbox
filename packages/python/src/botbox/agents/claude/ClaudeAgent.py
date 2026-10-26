import json
import math
import shlex
import shutil
from pathlib import Path
from typing import Any

CREDENTIALS = ".credentials.json"
API_KEY = "api_key"


class ClaudeAgent:
    """Claude Code."""

    image = "botbox-claude:latest"
    dockerfile = Path(__file__).with_name("Dockerfile")
    home = "/home/user"
    sessions_dir = ".claude/projects"
    allow: tuple[str, ...] = ("api.anthropic.com",)

    def __init__(
        self,
        model: str | None = None,
        effort: str | None = None,
        *,
        api_key: str | None = None,
        host_home: Path | None = None,
        tool_timeout: float = 0,
    ) -> None:
        if tool_timeout < 0:
            raise ValueError(f"tool_timeout is in seconds and must be 0 or more: {tool_timeout!r}")
        self.model = model
        self.effort = effort
        self.api_key = api_key
        self.tool_timeout = tool_timeout
        self.host_home = Path.home() / ".claude" if host_home is None else host_home

    def _env(self) -> str:
        if not self.tool_timeout:
            return ""
        ms = math.ceil(self.tool_timeout * 1000)
        # Without the last var, a Bash call that times out is moved to the background, not killed.
        return (
            f"BASH_DEFAULT_TIMEOUT_MS={ms} BASH_MAX_TIMEOUT_MS={ms}"
            " CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1 "
        )

    def command(self, prompt: str) -> str:
        command = self._env() + (
            f"claude -p {shlex.quote(prompt)} --output-format json --dangerously-skip-permissions"
            " --strict-mcp-config"
        )
        if self.model is not None:
            command += f" --model {shlex.quote(self.model)}"
        if self.effort is not None:
            command += f" --effort {shlex.quote(self.effort)}"
        return command

    def session_command(self) -> str:
        command = self._env() + (
            "claude -p --input-format stream-json --output-format stream-json --verbose"
            " --dangerously-skip-permissions --strict-mcp-config"
        )
        if self.model is not None:
            command += f" --model {shlex.quote(self.model)}"
        if self.effort is not None:
            command += f" --effort {shlex.quote(self.effort)}"
        return command

    def encode(self, message: str) -> str:
        return json.dumps({"type": "user", "message": {"role": "user", "content": message}})

    def turn_ended(self, event: dict[str, Any]) -> bool:
        return bool(event.get("type") == "result")

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
