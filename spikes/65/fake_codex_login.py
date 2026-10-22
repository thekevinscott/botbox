"""Print a placeholder Codex auth.json: unsigned tokens, no refresh token, nothing usable.

  fake_codex_login.py <host auth.json>

Keeps the account id and plan type, which Codex sends as headers and reads to pick
defaults. They identify the account but don't authenticate it.
"""

import base64
import json
import sys
import time
from datetime import UTC, datetime


def b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def jwt(claims: dict) -> str:
    return f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(claims)}.placeholder"


def claims_of(token: str) -> dict:
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


real = json.loads(open(sys.argv[1]).read())["tokens"]
account = real["account_id"]
plan = claims_of(real["id_token"])["https://api.openai.com/auth"]["chatgpt_plan_type"]
auth = {"chatgpt_account_id": account, "chatgpt_plan_type": plan}
now = int(time.time())
far = now + 10 * 365 * 86400
print(
    json.dumps(
        {
            "auth_mode": "chatgpt",
            "OPENAI_API_KEY": None,
            "tokens": {
                "id_token": jwt(
                    {"email": "placeholder@example.com", "https://api.openai.com/auth": auth,
                     "iat": now, "exp": far}
                ),
                "access_token": jwt({"https://api.openai.com/auth": auth, "iat": now, "exp": far}),
                "refresh_token": "placeholder",
                "account_id": account,
            },
            "last_refresh": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
    )
)
