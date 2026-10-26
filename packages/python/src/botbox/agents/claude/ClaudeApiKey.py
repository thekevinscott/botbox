from collections.abc import Mapping

from botbox.credential_proxy import PROXY_URL, Credential, Injection

# Claude Code sends apiKeyHelper's value as both x-api-key and a Bearer Authorization.
INJECTION = Injection(
    "api.anthropic.com", "/v1/messages(/count_tokens)?", "x-api-key", ("Authorization",)
)
PLACEHOLDER = "sk-ant-api03-botbox-placeholder"


class ClaudeApiKey:
    """An Anthropic API key. The credential proxy sends it upstream as `x-api-key`, and the box
    gets a placeholder key that points Claude Code at the proxy."""

    env: Mapping[str, str] = {"ANTHROPIC_BASE_URL": PROXY_URL}
    placeholder = PLACEHOLDER

    def __init__(self, key: str) -> None:
        self._key = key

    def __repr__(self) -> str:
        return "ClaudeApiKey(...)"

    def read(self) -> Credential:
        """The key, as the proxy sends it."""
        return Credential(INJECTION, self._key)
