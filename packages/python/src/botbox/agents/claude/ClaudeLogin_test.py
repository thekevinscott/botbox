import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from botbox.agents.claude.ClaudeLogin import NEVER_MS, ClaudeLogin

MODULE = f"{__package__}.ClaudeLogin"
NOW_MS = 1_800_000_000_000


class Expired(Exception):
    """Stands in for `CredentialsExpired`."""

    def __init__(self, path: Path, expired: datetime) -> None:
        self.path = path
        self.expired = expired


@pytest.fixture(autouse=True)
def collaborators() -> Iterator[None]:
    with (
        patch(f"{MODULE}.PROXY_URL", "http://proxy"),
        patch(f"{MODULE}.Credential", lambda injection, secret: (injection, secret)),
        patch(f"{MODULE}.INJECTION", "injection"),
        patch(f"{MODULE}.CredentialsExpired", Expired),
        patch(f"{MODULE}.time.time", lambda: NOW_MS / 1000),
    ):
        yield


def oauth(**fields: Any) -> dict[str, Any]:
    return {
        "accessToken": "sk-ant-oat01-real",
        "refreshToken": "sk-ant-ort01-real",
        "expiresAt": NOW_MS + 1,
        "scopes": ["user:inference"],
        "subscriptionType": "max",
        **fields,
    }


@pytest.fixture
def path(tmp_path: Path) -> Path:
    path = tmp_path / ".credentials.json"
    path.write_text(json.dumps({"claudeAiOauth": oauth(), "mcpOAuth": {"s": "secret"}}))
    return path


def describe_ClaudeLogin() -> None:
    def it_keeps_its_path(path: Path) -> None:
        assert ClaudeLogin(path).path == path

    def describe_read() -> None:
        def it_sends_the_access_token_as_a_bearer(path: Path) -> None:
            read: object = ClaudeLogin(path).read()
            assert read == ("injection", "Bearer sk-ant-oat01-real")

        @pytest.mark.parametrize("expires", [NOW_MS, NOW_MS - 1])
        def it_refuses_a_login_that_has_expired(path: Path, expires: int) -> None:
            path.write_text(json.dumps({"claudeAiOauth": oauth(expiresAt=expires)}))
            with pytest.raises(Expired) as raised:
                ClaudeLogin(path).read()
            assert raised.value.path == path
            assert raised.value.expired == datetime.fromtimestamp(expires / 1000, UTC)

        def it_raises_for_a_missing_file(tmp_path: Path) -> None:
            with pytest.raises(FileNotFoundError):
                ClaudeLogin(tmp_path / "missing").read()

        @pytest.mark.parametrize(
            "text",
            [
                "{",
                "[]",
                "{}",
                '{"claudeAiOauth": []}',
                json.dumps({"claudeAiOauth": oauth(accessToken=None)}),
                json.dumps({"claudeAiOauth": oauth(expiresAt="soon")}),
                json.dumps({"claudeAiOauth": {"expiresAt": NOW_MS + 1}}),
                json.dumps({"claudeAiOauth": {"accessToken": "t"}}),
            ],
        )
        def it_raises_value_error_for_a_file_with_no_login(path: Path, text: str) -> None:
            path.write_text(text)
            with pytest.raises(ValueError):
                ClaudeLogin(path).read()

        def it_names_the_file_with_no_login(path: Path) -> None:
            path.write_text("{}")
            with pytest.raises(ValueError, match=rf"^{path} holds no Claude Code login$"):
                ClaudeLogin(path).read()

    def describe_placeholder() -> None:
        def it_keeps_the_plan_and_scopes_and_drops_every_real_token(path: Path) -> None:
            assert json.loads(ClaudeLogin(path).placeholder()) == {
                "claudeAiOauth": {
                    "accessToken": "sk-ant-oat01-botbox-placeholder",
                    "refreshToken": "sk-ant-ort01-botbox-placeholder",
                    "expiresAt": NEVER_MS,
                    "scopes": ["user:inference"],
                    "subscriptionType": "max",
                }
            }

        def it_never_expires() -> None:
            assert NEVER_MS == 4102444800000

        def it_moves_the_refresh_tokens_expiry_too_when_the_host_has_one(path: Path) -> None:
            path.write_text(json.dumps({"claudeAiOauth": oauth(refreshTokenExpiresAt=NOW_MS)}))
            placeholder = json.loads(ClaudeLogin(path).placeholder())["claudeAiOauth"]
            assert placeholder["refreshTokenExpiresAt"] == NEVER_MS

        def it_is_made_from_an_expired_login_too(path: Path) -> None:
            path.write_text(json.dumps({"claudeAiOauth": oauth(expiresAt=0)}))
            assert json.loads(ClaudeLogin(path).placeholder())["claudeAiOauth"]["expiresAt"] == (
                NEVER_MS
            )

        def it_raises_for_a_file_with_no_login(path: Path) -> None:
            path.write_text("{}")
            with pytest.raises(ValueError, match="holds no Claude Code login"):
                ClaudeLogin(path).placeholder()

    def describe_env() -> None:
        def it_points_claude_code_at_the_proxy() -> None:
            assert ClaudeLogin.env == {"ANTHROPIC_BASE_URL": "http://127.0.0.1:41894"}
