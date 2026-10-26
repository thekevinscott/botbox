import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import json5

from botbox.credential_proxy import PROXY_URL, Credential, Injection

PROVIDER = "openrouter"
INJECTION = Injection("openrouter.ai", "/api/v1/chat/completions", "Authorization")
PLACEHOLDER = "sk-or-v1-botbox-placeholder"
BASE_URL = f"{PROXY_URL}/api/v1"
# pi reads a key that names a set env var as that var's value.
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
SECRETS = ("apiKey", "headers")
# A model's own baseUrl would go around the proxy.
MODEL_SECRETS = ("headers", "baseUrl")


class OpenRouterKey:
    """An OpenRouter key: `api_key`, or the host's in pi's `auth.json`. The credential proxy
    sends it upstream, and the box gets a placeholder key and a provider pointed at the proxy."""

    # pi takes the proxy from models.json.
    env: Mapping[str, str] = {}

    def __init__(self, auth: Path, api_key: str | None = None) -> None:
        self.auth = auth
        self._api_key = api_key

    def read(self) -> Credential:
        """The key as a Bearer credential. Raises `OSError`, or `ValueError` for an `auth.json`
        with no OpenRouter key or one that is a command or an env var name."""
        key = self._api_key if self._api_key is not None else self._host_key()
        return Credential(INJECTION, f"Bearer {key}")

    def placeholder(self) -> str:
        """`auth.json` for the box: a placeholder key for OpenRouter alone."""
        return json.dumps({PROVIDER: {"type": "api_key", "key": PLACEHOLDER}})

    def models(self, host: Path | None) -> str:
        """`models.json` for the box: OpenRouter from the host's `models.json` at `host`, if
        any, pointed at the proxy and stripped of keys and headers. Other providers are left
        out."""
        providers = json5.loads(host.read_text()).get("providers", {}) if host else {}
        provider = {k: v for k, v in providers.get(PROVIDER, {}).items() if k not in SECRETS}
        for field in ("models", "modelOverrides"):
            if field in provider:
                provider[field] = _without_secrets(provider[field])
        return json.dumps({"providers": {PROVIDER: {**provider, "baseUrl": BASE_URL}}})

    def _host_key(self) -> str:
        entry = json.loads(self.auth.read_text())
        entry = entry.get(PROVIDER) if isinstance(entry, dict) else None
        key = entry.get("key") if isinstance(entry, dict) else None
        if not isinstance(key, str) or not key:
            raise ValueError(f"{self.auth} holds no OpenRouter key")
        if key.startswith("!") or ENV_NAME.fullmatch(key):
            raise ValueError(
                f"the OpenRouter key in {self.auth} is a command or an env var name; botbox"
                " sends only a literal key"
            )
        return key


def _without_secrets(models: Any) -> Any:
    """`models`, a list or a dict of model entries, with each entry's `MODEL_SECRETS` dropped."""

    def strip(entry: Any) -> Any:
        if not isinstance(entry, dict):
            return entry
        return {k: v for k, v in entry.items() if k not in MODEL_SECRETS}

    if isinstance(models, list):
        return [strip(entry) for entry in models]
    if isinstance(models, dict):
        return {name: strip(entry) for name, entry in models.items()}
    return models
