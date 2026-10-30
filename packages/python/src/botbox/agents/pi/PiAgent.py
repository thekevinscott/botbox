import shlex
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

import json5

from botbox.agents.Agent import Agent
from botbox.agents.HomeFiles import HomeFiles
from botbox.agents.pi.OpenRouterKey import OpenRouterKey
from botbox.agents.with_env import with_env

AUTH = "auth.json"
MODELS = "models.json"
AGENT_DIR = ".pi/agent"
TOOL_TIMEOUT_EXTENSION = "/usr/local/lib/botbox/tool-timeout.ts"


def resolve_allow(provider: str, model: str | None, models: Path, staged: bool) -> tuple[str, ...]:
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


class PiAgent(Agent):
    """pi, on OpenRouter or any provider defined in models.json."""

    image = "botbox-pi:latest"
    dockerfile = Path(__file__).with_name("Dockerfile")
    home = "/home/user"
    sessions_dir = ".pi/agent/sessions"
    allow: tuple[str, ...]
    """On OpenRouter, nothing: the credential proxy reaches it."""
    credential_source: OpenRouterKey | None
    """The OpenRouter key, which the proxy sends upstream, or None for a custom provider, whose
    credentials are copied in."""

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
        if provider == "openrouter":
            self.allow = ()
            self.credential_source = OpenRouterKey(self.host_home / AUTH, api_key)
        else:
            self.allow = resolve_allow(
                provider, model, self.host_home / MODELS, staged=api_key is None
            )
            self.credential_source = None

    def command(self, prompt: str) -> str:
        command = f"pi -p {shlex.quote(prompt)} --mode json"
        # pi 1.0 rejects --provider without --model; before, it ignored it and picked the default.
        if self.model is not None:
            command += f" --provider {shlex.quote(self.provider)} --model {shlex.quote(self.model)}"
        if self.tool_timeout:
            command += f" -e {TOOL_TIMEOUT_EXTENSION}"
        return with_env(self.env, command)

    def stage_auth(self, home: HomeFiles) -> None:
        if self.credential_source is not None:
            home.write(f"{AGENT_DIR}/{AUTH}", self.credential_source.placeholder(), mode=0o600)
            host = self.host_home / MODELS
            staged = self.api_key is None and host.is_file()
            models = self.credential_source.models(host if staged else None)
            home.write(f"{AGENT_DIR}/{MODELS}", models)
            return
        # A custom provider is defined in models.json, so __init__ found one.
        home.write(f"{AGENT_DIR}/{AUTH}", (self.host_home / AUTH).read_bytes(), mode=0o600)
        home.write(f"{AGENT_DIR}/{MODELS}", (self.host_home / MODELS).read_bytes(), mode=0o600)
