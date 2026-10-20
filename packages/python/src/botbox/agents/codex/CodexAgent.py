import json
import shlex
import shutil
from pathlib import Path

AUTH = "auth.json"


class CodexAgent:
    """The OpenAI Codex CLI."""

    image = "botbox-codex:latest"
    dockerfile = Path(__file__).with_name("Dockerfile")
    home = "/home/user"
    transcripts = ".codex/sessions/**/*.jsonl"

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
        self.allow = ("chatgpt.com",) if api_key is None else ("api.openai.com",)
        self.host_home = Path.home() / ".codex" if host_home is None else host_home

    def command(self, prompt: str) -> str:
        command = (
            "codex exec --json --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check"
            " --disable plugins"
        )
        if self.model is not None:
            command += f" --model {self.model}"
        if self.effort is not None:
            command += f" --config model_reasoning_effort={self.effort}"
        return f"{command} {shlex.quote(prompt)}"

    def stage_auth(self, home: Path) -> None:
        destination = home / ".codex"
        destination.mkdir()
        if self.api_key is None:
            shutil.copy(self.host_home / AUTH, destination / AUTH)
            return
        auth = destination / AUTH
        auth.touch(mode=0o600)
        auth.write_text(json.dumps({"auth_mode": "apikey", "OPENAI_API_KEY": self.api_key}))
