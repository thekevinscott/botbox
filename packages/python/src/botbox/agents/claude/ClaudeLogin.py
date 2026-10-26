import json
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from botbox.credential_proxy import PROXY_URL, Credential, CredentialsExpired, Injection

INJECTION = Injection(
    "api.anthropic.com", "/v1/messages(/count_tokens)?", "Authorization", ("x-api-key",)
)
ACCESS_PLACEHOLDER = "sk-ant-oat01-botbox-placeholder"
REFRESH_PLACEHOLDER = "sk-ant-ort01-botbox-placeholder"
# 2100-01-01, in ms. A login that never expires is one Claude Code never tries to refresh.
NEVER_MS = 4102444800000


class ClaudeLogin:
    """The host's Claude Code login. The credential proxy sends its access token upstream, and
    the box gets a placeholder login that points Claude Code at the proxy."""

    env: Mapping[str, str] = {"ANTHROPIC_BASE_URL": PROXY_URL}

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> Credential:
        """The access token as a Bearer credential. Raises `CredentialsExpired` once it has
        expired, `OSError`, or `ValueError` for a file with no login in it."""
        oauth = self._oauth()
        if oauth["expiresAt"] <= time.time() * 1000:
            expired = datetime.fromtimestamp(oauth["expiresAt"] / 1000, UTC)
            raise CredentialsExpired(self.path, expired)
        return Credential(INJECTION, f"Bearer {oauth['accessToken']}")

    def placeholder(self) -> str:
        """The login for the box: the host's plan and scopes, no real token, never expiring."""
        oauth = {
            **self._oauth(),
            "accessToken": ACCESS_PLACEHOLDER,
            "refreshToken": REFRESH_PLACEHOLDER,
            "expiresAt": NEVER_MS,
        }
        if "refreshTokenExpiresAt" in oauth:
            oauth["refreshTokenExpiresAt"] = NEVER_MS
        return json.dumps({"claudeAiOauth": oauth})

    def _oauth(self) -> dict[str, Any]:
        login = json.loads(self.path.read_text())
        oauth = login.get("claudeAiOauth") if isinstance(login, dict) else None
        if (
            not isinstance(oauth, dict)
            or not isinstance(oauth.get("accessToken"), str)
            or not isinstance(oauth.get("expiresAt"), int | float)
        ):
            raise ValueError(f"{self.path} holds no Claude Code login")
        return oauth
