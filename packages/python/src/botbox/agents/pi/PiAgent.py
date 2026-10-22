import json
import shlex
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROVIDER_HOSTS = {"openrouter": ("openrouter.ai",)}

AUTH = "auth.json"
MODELS = "models.json"


def resolve_allow(provider: str, models: Path, *, staged: bool) -> tuple[str, ...]:
    if provider in PROVIDER_HOSTS:
        return PROVIDER_HOSTS[provider]
    if not staged:
        raise ValueError(
            f"provider {provider!r} is not built in, and with api_key no {MODELS} is staged"
        )
    providers = json.loads(models.read_text()).get("providers", {}) if models.is_file() else {}
    if provider not in providers:
        raise ValueError(f"provider {provider!r} is not built in and not defined in {models}")
    host = urlparse(providers[provider].get("baseUrl", "")).hostname
    if not host:
        raise ValueError(f"provider {provider!r} in {models} has no baseUrl with a host")
    return (host,)


class PiAgent:
    """pi, on OpenRouter or any provider defined in models.json."""

    image = "botbox-pi:latest"
    dockerfile = Path(__file__).with_name("Dockerfile")
    home = "/home/user"
    transcripts = ".pi/agent/sessions/**/*.jsonl"

    def __init__(
        self,
        provider: str,
        model: str | None = None,
        *,
        api_key: str | None = None,
        host_home: Path | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.host_home = Path.home() / ".pi" / "agent" if host_home is None else host_home
        self.allow = resolve_allow(provider, self.host_home / MODELS, staged=api_key is None)

    def command(self, prompt: str) -> str:
        command = f"pi -p {shlex.quote(prompt)} --mode json --provider {shlex.quote(self.provider)}"
        if self.model is not None:
            command += f" --model {shlex.quote(self.model)}"
        return command

    def session_command(self) -> str:
        command = f"pi --mode rpc --provider {shlex.quote(self.provider)}"
        if self.model is not None:
            command += f" --model {shlex.quote(self.model)}"
        return command

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
