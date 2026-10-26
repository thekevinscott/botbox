import json
import shlex
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import json5

from botbox.agents.with_env import with_env

PROVIDER_HOSTS = {"openrouter": ("openrouter.ai",)}

AUTH = "auth.json"
MODELS = "models.json"
TOOL_TIMEOUT_EXTENSION = "/usr/local/lib/botbox/tool-timeout.ts"

# Each update resends the whole partial message, so a turn's output grows with its square.
# message_end and tool_execution_end carry the final versions. pi writes `type` first.
DROP_UPDATES = shlex.join(
    [
        "sed",
        "-u",
        "-e",
        '/^{"type":"message_update"/d',
        "-e",
        '/^{"type":"tool_execution_update"/d',
    ]
)


def drop_updates(command: str) -> str:
    """`command` with pi's streaming update events dropped inside the container."""
    # Not grep -v: it exits 1 on empty output, which pipefail would report as a failure.
    return "exec bash -o pipefail -c " + shlex.quote(f"{command} | {DROP_UPDATES}")


def resolve_allow(provider: str, model: str | None, models: Path, staged: bool) -> tuple[str, ...]:
    if provider in PROVIDER_HOSTS:
        return PROVIDER_HOSTS[provider]
    if not staged:
        raise ValueError(
            f"provider {provider!r} is not built in, and with api_key no {MODELS} is staged"
        )
    providers = json5.loads(models.read_text()).get("providers", {}) if models.is_file() else {}
    if provider not in providers:
        raise ValueError(f"provider {provider!r} is not built in and not defined in {models}")
    config = providers[provider]
    entries = config.get("models", [])
    selected = [entry for entry in entries if model is None or entry.get("id") == model]
    urls = [entry.get("baseUrl") or config.get("baseUrl", "") for entry in selected]
    if model is None or not selected:
        urls.insert(0, config.get("baseUrl", ""))
    hosts = tuple(dict.fromkeys(host for url in urls if (host := urlparse(url).hostname)))
    if not hosts:
        raise ValueError(f"provider {provider!r} in {models} has no baseUrl with a host")
    return hosts


class PiAgent:
    """pi, on OpenRouter or any provider defined in models.json."""

    image = "botbox-pi:latest"
    dockerfile = Path(__file__).with_name("Dockerfile")
    home = "/home/user"
    sessions_dir = ".pi/agent/sessions"

    def __init__(
        self,
        provider: str,
        model: str | None = None,
        *,
        api_key: str | None = None,
        host_home: Path | None = None,
        tool_timeout: float = 0,
    ) -> None:
        if tool_timeout < 0:
            raise ValueError(f"tool_timeout is in seconds and must be 0 or more: {tool_timeout!r}")
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.tool_timeout = tool_timeout
        self.env: Mapping[str, str] = (
            {"BOTBOX_TOOL_TIMEOUT": f"{tool_timeout:g}"} if tool_timeout else {}
        )
        self.host_home = Path.home() / ".pi" / "agent" if host_home is None else host_home
        self.allow = resolve_allow(provider, model, self.host_home / MODELS, staged=api_key is None)

    def command(self, prompt: str) -> str:
        return drop_updates(self._pi(f"-p {shlex.quote(prompt)} --mode json"))

    def session_command(self) -> str:
        return drop_updates(self._pi("--mode rpc"))

    def _pi(self, mode: str) -> str:
        command = f"pi {mode} --provider {shlex.quote(self.provider)}"
        if self.model is not None:
            command += f" --model {shlex.quote(self.model)}"
        if self.tool_timeout:
            command += f" -e {TOOL_TIMEOUT_EXTENSION}"
        return with_env(self.env, command)

    def encode(self, message: str) -> str:
        return json.dumps({"type": "prompt", "message": message})

    def turn_ended(self, event: dict[str, Any]) -> bool:
        return bool(event.get("type") == "agent_end")

    def stage_auth(self, home: Path) -> None:
        destination = home / ".pi" / "agent"
        destination.mkdir(parents=True)
        if self.api_key is not None:
            auth = destination / AUTH
            auth.touch(mode=0o600)
            auth.write_text(json.dumps({self.provider: {"type": "api_key", "key": self.api_key}}))
            return
        shutil.copy(self.host_home / AUTH, destination / AUTH)
        if (self.host_home / MODELS).is_file():
            shutil.copy(self.host_home / MODELS, destination / MODELS)
