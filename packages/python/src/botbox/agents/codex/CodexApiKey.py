import json
from collections.abc import Mapping

from botbox.credential_proxy import PROXY_URL, Credential, Injection

INJECTION = Injection("api.openai.com", "/v1/responses", "Authorization")
PLACEHOLDER = "sk-botbox-placeholder"


class CodexApiKey:
    """An OpenAI API key. The credential proxy sends it upstream, and the box gets a
    placeholder."""

    env: Mapping[str, str] = {}
    base_url = f"{PROXY_URL}/v1"

    def __init__(self, key: str) -> None:
        self._key = key

    def __repr__(self) -> str:
        return "CodexApiKey(...)"

    def read(self) -> Credential:
        """The key as a Bearer credential."""
        return Credential(INJECTION, f"Bearer {self._key}")

    def placeholder(self) -> str:
        """The login for the box: API-key mode with a key that is not the real one."""
        return json.dumps({"auth_mode": "apikey", "OPENAI_API_KEY": PLACEHOLDER})
