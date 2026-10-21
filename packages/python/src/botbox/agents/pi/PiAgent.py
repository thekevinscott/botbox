import json
import os
import shlex
import shutil
from pathlib import Path
from typing import Any

PROVIDER_HOSTS = {"openrouter": ("openrouter.ai",)}

PROVIDER_HOST_VARIABLES = {"tower": "PI_AGENT_HOST"}

PROVIDERS = (*PROVIDER_HOSTS, *PROVIDER_HOST_VARIABLES)

AUTH = "auth.json"
MODELS = "models.json"


def resolve_allow(provider: str) -> tuple[str, ...]:
    if provider in PROVIDER_HOSTS:
        return PROVIDER_HOSTS[provider]
    variable = PROVIDER_HOST_VARIABLES[provider]
    host = os.environ.get(variable)
    if not host:
        raise ValueError(f"provider {provider!r} needs {variable} set to the host it serves from")
    return (host,)


class PiAgent:
    """pi, on OpenRouter or a local model host."""

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
        if provider not in PROVIDERS:
            raise ValueError(f"unknown provider {provider!r}: expected {', '.join(PROVIDERS)}")
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.allow = resolve_allow(provider)
        self.host_home = Path.home() / ".pi" / "agent" if host_home is None else host_home

    def command(self, prompt: str) -> str:
        command = f"pi -p {shlex.quote(prompt)} --mode json --provider {self.provider}"
        if self.model is not None:
            command += f" --model {shlex.quote(self.model)}"
        return command

    def session_command(self) -> str:
        command = f"pi --mode rpc --provider {self.provider}"
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
