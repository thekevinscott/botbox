import base64
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from botbox.agents.codex.CodexLogin import (
    AUTH_CLAIMS,
    NEVER,
    CodexLogin,
    jwt_claims,
    unsigned_jwt,
)

MODULE = f"{__package__}.CodexLogin"
NOW = 1_800_000_000


class Expired(Exception):
    """Stands in for `CredentialsExpired`."""

    def __init__(self, path: Path, expired: datetime) -> None:
        self.path = path
        self.expired = expired


@pytest.fixture(autouse=True)
def collaborators() -> Iterator[None]:
    with (
        patch(f"{MODULE}.Credential", lambda injection, secret: (injection, secret)),
        patch(f"{MODULE}.INJECTION", "injection"),
        patch(f"{MODULE}.CredentialsExpired", Expired),
        patch(f"{MODULE}.time.time", lambda: NOW),
    ):
        yield


def jwt(claims: dict[str, Any]) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"eyJhbGciOiJSUzI1NiJ9.{payload}.real-signature"


def tokens(**fields: Any) -> dict[str, Any]:
    auth = {"chatgpt_account_id": "acct-1", "chatgpt_plan_type": "plus", "chatgpt_user_id": "u"}
    return {
        "id_token": jwt({"email": "me@example.com", AUTH_CLAIMS: auth, "exp": NOW + 60}),
        "access_token": jwt({AUTH_CLAIMS: auth, "exp": NOW + 1}),
        "refresh_token": "rt-real",
        "account_id": "acct-1",
        **fields,
    }


@pytest.fixture
def path(tmp_path: Path) -> Path:
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"auth_mode": "chatgpt", "tokens": tokens()}))
    return path


def describe_jwt_claims() -> None:
    def it_reads_an_unpadded_payload() -> None:
        assert jwt_claims(jwt({"a": "bc"})) == {"a": "bc"}

    @pytest.mark.parametrize("token", ["", "a.b", "a.b.c.d", "a.!!.c", f"a.{'W10'}.c"])
    def it_raises_value_error_for_anything_else(token: str) -> None:
        with pytest.raises(ValueError):
            jwt_claims(token)


def describe_unsigned_jwt() -> None:
    def it_carries_the_claims() -> None:
        assert jwt_claims(unsigned_jwt({"exp": 1})) == {"exp": 1}

    def it_is_unsigned() -> None:
        header, _, signature = unsigned_jwt({}).split(".")
        assert jwt_claims(f"x.{header}.x") == {"alg": "none", "typ": "JWT"}
        assert signature == "botbox-placeholder"


def describe_CodexLogin() -> None:
    def it_keeps_its_path(path: Path) -> None:
        assert CodexLogin(path).path == path

    def it_points_codex_at_the_proxys_codex_backend() -> None:
        assert CodexLogin.base_url == "http://127.0.0.1:41894/backend-api/codex"

    def it_needs_no_environment() -> None:
        assert CodexLogin.env == {}

    def describe_read() -> None:
        def it_sends_the_access_token_as_a_bearer(path: Path) -> None:
            read: object = CodexLogin(path).read()
            assert read == ("injection", f"Bearer {tokens()['access_token']}")

        @pytest.mark.parametrize("expires", [NOW, NOW - 1])
        def it_refuses_a_token_that_has_expired(path: Path, expires: int) -> None:
            expired = tokens(access_token=jwt({"exp": expires}))
            path.write_text(json.dumps({"tokens": expired}))
            with pytest.raises(Expired) as raised:
                CodexLogin(path).read()
            assert raised.value.path == path
            assert raised.value.expired == datetime.fromtimestamp(expires, UTC)

        def it_raises_for_a_missing_file(tmp_path: Path) -> None:
            with pytest.raises(FileNotFoundError):
                CodexLogin(tmp_path / "missing").read()

        @pytest.mark.parametrize(
            "text",
            [
                "{",
                "[]",
                '{"auth_mode": "apikey", "OPENAI_API_KEY": "sk"}',
                '{"tokens": []}',
                json.dumps({"tokens": tokens(access_token=None)}),
                json.dumps({"tokens": tokens(id_token=None)}),
                json.dumps({"tokens": tokens(access_token="opaque")}),
                json.dumps({"tokens": tokens(access_token=jwt({}))}),
                json.dumps({"tokens": tokens(access_token=jwt({"exp": "soon"}))}),
            ],
        )
        def it_raises_value_error_for_a_file_with_no_usable_login(path: Path, text: str) -> None:
            path.write_text(text)
            with pytest.raises(ValueError):
                CodexLogin(path).read()

        def it_names_the_file_with_no_login(path: Path) -> None:
            path.write_text("{}")
            with pytest.raises(ValueError, match=rf"^{path} holds no Codex ChatGPT login$"):
                CodexLogin(path).read()

        def it_names_the_file_with_a_token_that_is_not_a_jwt(path: Path) -> None:
            path.write_text(json.dumps({"tokens": tokens(access_token="opaque")}))
            with pytest.raises(ValueError, match=rf"^{path} holds a token that is not a JWT$"):
                CodexLogin(path).read()

    def describe_placeholder() -> None:
        def placeholder(path: Path) -> dict[str, Any]:
            login: dict[str, Any] = json.loads(CodexLogin(path).placeholder())
            return login

        def it_holds_no_real_token(path: Path) -> None:
            text = CodexLogin(path).placeholder()
            for name, value in tokens().items():
                if name != "account_id":
                    assert value not in text
            assert "me@example.com" not in text
            assert '"u"' not in text

        def it_keeps_the_account_id_and_plan(path: Path) -> None:
            login = placeholder(path)
            assert login["auth_mode"] == "chatgpt"
            assert login["OPENAI_API_KEY"] is None
            assert login["tokens"]["account_id"] == "acct-1"
            auth = {"chatgpt_account_id": "acct-1", "chatgpt_plan_type": "plus"}
            for name in ("id_token", "access_token"):
                assert jwt_claims(login["tokens"][name])[AUTH_CLAIMS] == auth

        def it_never_expires(path: Path) -> None:
            login = placeholder(path)
            assert jwt_claims(login["tokens"]["access_token"])["exp"] == NEVER
            assert jwt_claims(login["tokens"]["id_token"])["exp"] == NEVER
            assert NEVER == 4102444800

        def it_has_no_usable_refresh_token(path: Path) -> None:
            assert placeholder(path)["tokens"]["refresh_token"] == "botbox-placeholder"

        def it_was_just_refreshed(path: Path) -> None:
            refreshed = datetime.fromisoformat(placeholder(path)["last_refresh"])
            assert refreshed == datetime.fromtimestamp(NOW, UTC)

        def it_takes_the_account_id_from_the_id_token_when_the_login_has_none(
            path: Path,
        ) -> None:
            path.write_text(json.dumps({"tokens": tokens(account_id=None)}))
            assert placeholder(path)["tokens"]["account_id"] == "acct-1"

        def it_is_made_from_an_expired_login_too(path: Path) -> None:
            path.write_text(json.dumps({"tokens": tokens(access_token=jwt({"exp": 0}))}))
            assert placeholder(path)["tokens"]["account_id"] == "acct-1"

        def it_raises_for_a_file_with_no_login(path: Path) -> None:
            path.write_text("{}")
            with pytest.raises(ValueError, match="holds no Codex ChatGPT login"):
                CodexLogin(path).placeholder()
