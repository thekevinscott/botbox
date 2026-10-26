import json
import shlex
from pathlib import Path
from typing import Any

from botbox.agents.codex.CodexApiKey import CodexApiKey
from botbox.agents.codex.CodexLogin import CodexLogin
from botbox.credential_proxy import PROXY_URL

AUTH = "auth.json"
CONFIG = "config.toml"
# chatgpt_base_url sends Codex's account and settings calls to the proxy, which refuses them,
# rather than past it.
PROVIDER_CONFIG = """\
model_provider = "botbox"
chatgpt_base_url = {chatgpt_base_url}

[model_providers.botbox]
name = "botbox"
base_url = {base_url}
wire_api = "responses"
requires_openai_auth = true
"""

NO_SESSION = (
    "NOT IMPLEMENTED: CodexAgent has no session mode. For a Codex model in a session, use"
    " PiAgent('openrouter', 'openai/<model>')."
)

NO_TOOL_TIMEOUT = (
    "NOT IMPLEMENTED: CodexAgent has no tool_timeout. Codex has no setting that kills a shell"
    " command after a time limit."
)


class CodexAgent:
    """The OpenAI Codex CLI."""

    image = "botbox-codex:latest"
    dockerfile = Path(__file__).with_name("Dockerfile")
    home = "/home/user"
    sessions_dir = ".codex/sessions"
    allow: tuple[str, ...] = ()
    """Nothing: the credential proxy reaches the API for it."""
    credential_source: CodexLogin | CodexApiKey
    """The host's login or the API key, which the proxy sends upstream."""

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
        if tool_timeout:
            raise NotImplementedError(NO_TOOL_TIMEOUT)
        self.model = model
        self.effort = effort
        self.api_key = api_key
        self.host_home = Path.home() / ".codex" if host_home is None else host_home
        self.credential_source = (
            CodexLogin(self.host_home / AUTH) if api_key is None else CodexApiKey(api_key)
        )

    def command(self, prompt: str) -> str:
        command = (
            "codex exec --json --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check"
            " --disable plugins --disable apps --config analytics.enabled=false"
        )
        if self.model is not None:
            command += f" --model {shlex.quote(self.model)}"
        if self.effort is not None:
            command += f" --config {shlex.quote(f'model_reasoning_effort={self.effort}')}"
        return f"{command} {shlex.quote(prompt)}"

    def session_command(self) -> str:
        raise NotImplementedError(NO_SESSION)

    def encode(self, message: str) -> str:
        raise NotImplementedError(NO_SESSION)

    def turn_ended(self, event: dict[str, Any]) -> bool:
        raise NotImplementedError(NO_SESSION)

    def stage_auth(self, home: Path) -> None:
        """A placeholder login, and a model provider that points Codex at the credential proxy."""
        placeholder = self.credential_source.placeholder()
        destination = home / ".codex"
        destination.mkdir()
        auth = destination / AUTH
        auth.touch(mode=0o600)
        auth.write_text(placeholder)
        config = PROVIDER_CONFIG.format(
            base_url=json.dumps(self.credential_source.base_url),
            chatgpt_base_url=json.dumps(f"{PROXY_URL}/backend-api/"),
        )
        (destination / CONFIG).write_text(config)
