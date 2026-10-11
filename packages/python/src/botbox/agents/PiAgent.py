import os
import shutil
from pathlib import Path

PROVIDER_HOSTS = {"openrouter": ("openrouter.ai",)}

PROVIDER_HOST_VARIABLES = {"tower": "PI_AGENT_HOST"}

PROVIDERS = (*PROVIDER_HOSTS, *PROVIDER_HOST_VARIABLES)

AUTH_FILENAMES = ("auth.json", "models.json")


def resolve_allow(provider: str) -> tuple[str, ...]:
    if provider in PROVIDER_HOSTS:
        return PROVIDER_HOSTS[provider]
    variable = PROVIDER_HOST_VARIABLES[provider]
    host = os.environ.get(variable)
    if not host:
        raise ValueError(f"provider {provider!r} needs {variable} set to the host it serves from")
    return (host,)


class PiAgent:
    """pi. Image only: botbox builds it, but runs are not yet supported."""

    image = "botbox-pi:latest"
    dockerfile = Path(__file__).with_name("pi.Dockerfile")
    home = "/home/node"
    transcripts = ".pi/agent/sessions/**/*.jsonl"

    def __init__(self, provider: str, *, host_home: Path | None = None) -> None:
        if provider not in PROVIDERS:
            raise ValueError(f"unknown provider {provider!r}: expected {', '.join(PROVIDERS)}")
        self.provider = provider
        self.allow = resolve_allow(provider)
        self.host_home = Path.home() / ".pi" / "agent" if host_home is None else host_home

    def stage_auth(self, home: Path) -> None:
        destination = home / ".pi" / "agent"
        destination.mkdir(parents=True, exist_ok=True)
        for name in AUTH_FILENAMES:
            shutil.copy(self.host_home / name, destination / name)
