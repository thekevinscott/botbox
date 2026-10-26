import json
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from botbox.agents.codex.jwt_claims import jwt_claims
from botbox.agents.codex.unsigned_jwt import unsigned_jwt
from botbox.credential_proxy import PROXY_URL, Credential, CredentialsExpired, Injection

INJECTION = Injection(
    "chatgpt.com", "/backend-api/codex/(responses|models)", "Authorization", methods=("GET", "POST")
)
AUTH_CLAIMS = "https://api.openai.com/auth"
# 2100-01-01. An access token that never expires is one Codex never tries to refresh.
NEVER = 4102444800


class CodexLogin:
    """The host's Codex ChatGPT login. The credential proxy sends its access token upstream, and
    the box gets a placeholder login with no usable token in it."""

    env: Mapping[str, str] = {}
    base_url = f"{PROXY_URL}/backend-api/codex"

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> Credential:
        """The access token as a Bearer credential. Raises `CredentialsExpired` once it has
        expired, `OSError`, or `ValueError` for a file with no ChatGPT login in it."""
        access = self._tokens()["access_token"]
        expires = self._claims(access).get("exp")
        if not isinstance(expires, int | float):
            raise ValueError(f"{self.path} holds an access token with no expiry")
        if expires <= time.time():
            raise CredentialsExpired(self.path, datetime.fromtimestamp(expires, UTC))
        return Credential(INJECTION, f"Bearer {access}")

    def placeholder(self) -> str:
        """The login for the box: the host's account id and plan, unsigned tokens that never
        expire, and no refresh token."""
        tokens = self._tokens()
        host = self._claims(tokens["id_token"]).get(AUTH_CLAIMS)
        host = host if isinstance(host, dict) else {}
        account = tokens.get("account_id") or host.get("chatgpt_account_id")
        auth = {"chatgpt_account_id": account, "chatgpt_plan_type": host.get("chatgpt_plan_type")}
        now = int(time.time())
        claims = {AUTH_CLAIMS: auth, "iat": now, "exp": NEVER}
        return json.dumps(
            {
                "auth_mode": "chatgpt",
                "OPENAI_API_KEY": None,
                "tokens": {
                    "id_token": unsigned_jwt({**claims, "email": "placeholder@botbox.invalid"}),
                    "access_token": unsigned_jwt(claims),
                    "refresh_token": "botbox-placeholder",
                    "account_id": account,
                },
                "last_refresh": datetime.fromtimestamp(now, UTC).isoformat(),
            }
        )

    def _tokens(self) -> dict[str, Any]:
        login = json.loads(self.path.read_text())
        tokens = login.get("tokens") if isinstance(login, dict) else None
        if (
            not isinstance(tokens, dict)
            or not isinstance(tokens.get("access_token"), str)
            or not isinstance(tokens.get("id_token"), str)
        ):
            raise ValueError(f"{self.path} holds no Codex ChatGPT login")
        return tokens

    def _claims(self, token: str) -> dict[str, Any]:
        try:
            return jwt_claims(token)
        except ValueError as error:
            raise ValueError(f"{self.path} holds a token that is not a JWT") from error
