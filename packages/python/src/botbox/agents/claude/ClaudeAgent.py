import json
import math
import shlex
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from botbox.agents.Agent import Agent
from botbox.agents.claude.ClaudeApiKey import ClaudeApiKey
from botbox.agents.claude.ClaudeLogin import ClaudeLogin
from botbox.agents.HomeFiles import HomeFiles
from botbox.agents.Message import Message
from botbox.agents.message_from import message_from
from botbox.agents.with_env import with_env
from botbox.utils.json_object import json_object

CREDENTIALS = ".credentials.json"
API_KEY = "api_key"


class ClaudeMessageType(StrEnum):
    """stream-json's message lines, by their `type`."""

    # stdout also carries "system", "rate_limit_event" and "result" lines, which aren't messages.
    ASSISTANT = "assistant"
    USER = "user"


class ClaudeAgent(Agent):
    """Claude Code."""

    MESSAGE_TYPE = ClaudeMessageType

    image = "botbox-claude:latest"
    dockerfile = Path(__file__).with_name("Dockerfile")
    home = "/home/user"
    sessions_dir = ".claude/projects"
    allow: tuple[str, ...] = ()
    """Nothing: the credential proxy reaches the API for it."""
    credential_source: ClaudeLogin | ClaudeApiKey
    """The host's login or the `api_key`, which the proxy sends upstream."""

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
        self.env: Mapping[str, str] = {}
        if tool_timeout:
            ms = str(math.ceil(tool_timeout * 1000))
            # Without the last var, a timed-out Bash call is moved to the background, not killed.
            self.env = {
                "BASH_DEFAULT_TIMEOUT_MS": ms,
                "BASH_MAX_TIMEOUT_MS": ms,
                "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
            }
        self.host_home = Path.home() / ".claude" if host_home is None else host_home
        self.login = ClaudeLogin(self.host_home / CREDENTIALS)
        self.credential_source = self.login if api_key is None else ClaudeApiKey(api_key)

    def command(self, prompt: str) -> str:
        command = (
            f"claude -p {shlex.quote(prompt)} --output-format json --dangerously-skip-permissions"
            " --strict-mcp-config"
        )
        if self.model is not None:
            command += f" --model {shlex.quote(self.model)}"
        if self.effort is not None:
            command += f" --effort {shlex.quote(self.effort)}"
        return with_env(self.env, command)

    def session_command(self) -> str:
        command = (
            "claude -p --input-format stream-json --output-format stream-json --verbose"
            " --dangerously-skip-permissions --strict-mcp-config"
        )
        if self.model is not None:
            command += f" --model {shlex.quote(self.model)}"
        if self.effort is not None:
            command += f" --effort {shlex.quote(self.effort)}"
        return with_env(self.env, command)

    def encode(self, message: str) -> str:
        return json.dumps({"type": "user", "message": {"role": "user", "content": message}})

    def read_message(self, line: bytes) -> Message | None:
        event = json_object(line)
        if event is None or event.get("type") not in set(ClaudeMessageType):
            return None
        return message_from(event["type"], event.get("message"), event)

    def stage_auth(self, home: HomeFiles) -> None:
        if self.api_key is None:
            home.write(f".claude/{CREDENTIALS}", self.login.placeholder(), mode=0o600)
            return
        home.write(f".claude/{API_KEY}", ClaudeApiKey.placeholder, mode=0o600)
        helper = f"cat {self.home}/.claude/{API_KEY}"
        home.write(".claude/settings.json", json.dumps({"apiKeyHelper": helper}))
