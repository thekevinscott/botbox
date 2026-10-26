"""CodexAgent on a host login or a key: the box's home gets a placeholder, the proxy the secret."""

import base64
import json
import time
from pathlib import Path

import pytest
from staged_home_test import staged_home

from botbox import CodexAgent, CredentialsExpired, InjectingAgent

REFRESH = "rt-host-refresh"


def jwt(claims: dict[str, object]) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"eyJhbGciOiJSUzI1NiJ9.{payload}.host-signature"


def host_login(codex_home: Path, expires: float) -> dict[str, str]:
    codex_home.mkdir()
    auth = {"chatgpt_account_id": "acct-host", "chatgpt_plan_type": "pro"}
    tokens = {
        "id_token": jwt({"email": "me@example.com", "https://api.openai.com/auth": auth}),
        "access_token": jwt({"https://api.openai.com/auth": auth, "exp": int(expires)}),
        "refresh_token": REFRESH,
        "account_id": "acct-host",
    }
    login = {"auth_mode": "chatgpt", "OPENAI_API_KEY": None, "tokens": tokens}
    (codex_home / "auth.json").write_text(json.dumps(login))
    return tokens


def staged_codex(agent: CodexAgent, tmp_path: Path) -> Path:
    return staged_home(agent, tmp_path / "home") / ".codex"


def describe_a_codex_agent_on_the_host_login() -> None:
    def it_stages_a_home_that_holds_no_real_token(tmp_path: Path) -> None:
        tokens = host_login(tmp_path / "codex", time.time() + 3600)
        staged = staged_codex(CodexAgent(host_home=tmp_path / "codex"), tmp_path)
        text = (staged / "auth.json").read_text()
        for name in ("id_token", "access_token", "refresh_token"):
            assert tokens[name] not in text
        assert "me@example.com" not in text
        assert json.loads(text)["tokens"]["account_id"] == "acct-host"

    def it_hands_the_proxy_the_real_token_for_the_codex_backend(tmp_path: Path) -> None:
        tokens = host_login(tmp_path / "codex", time.time() + 3600)
        agent = CodexAgent(host_home=tmp_path / "codex")
        assert isinstance(agent, InjectingAgent)
        assert agent.allow == ()
        credential = agent.credential_source.read()
        assert credential.secret == f"Bearer {tokens['access_token']}"
        injection = credential.injection
        assert injection.upstream == "chatgpt.com"
        assert injection.paths == "/backend-api/codex/(responses|models)"
        assert injection.methods == ("GET", "POST")
        assert injection.header == "Authorization"

    def it_points_codex_at_the_proxy(tmp_path: Path) -> None:
        host_login(tmp_path / "codex", time.time() + 3600)
        staged = staged_codex(CodexAgent(host_home=tmp_path / "codex"), tmp_path)
        config = (staged / "config.toml").read_text()
        assert 'base_url = "http://127.0.0.1:41894/backend-api/codex"' in config

    def it_refuses_a_login_that_has_expired(tmp_path: Path) -> None:
        host_login(tmp_path / "codex", time.time() - 60)
        source = CodexAgent(host_home=tmp_path / "codex").credential_source
        with pytest.raises(CredentialsExpired, match="expired at"):
            source.read()


def describe_a_codex_agent_on_an_api_key() -> None:
    def it_stages_a_placeholder_key(tmp_path: Path) -> None:
        staged = staged_codex(CodexAgent(api_key="sk-host-key"), tmp_path)
        assert "sk-host-key" not in (staged / "auth.json").read_text()

    def it_hands_the_proxy_the_key_for_responses_only() -> None:
        credential = CodexAgent(api_key="sk-host-key").credential_source.read()
        assert credential.secret == "Bearer sk-host-key"
        assert credential.injection.upstream == "api.openai.com"
        assert credential.injection.paths == "/v1/responses"
        assert credential.injection.methods == ("POST",)
