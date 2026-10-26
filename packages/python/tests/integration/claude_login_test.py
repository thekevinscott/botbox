"""ClaudeAgent on a host login: the box's home gets a placeholder, the proxy gets the token."""

import json
import time
from pathlib import Path

import pytest

from botbox import ClaudeAgent, CredentialsExpired, InjectingAgent

ACCESS = "sk-ant-oat01-host-access"
REFRESH = "sk-ant-ort01-host-refresh"


def host_login(claude_home: Path, expires_at: float) -> None:
    claude_home.mkdir()
    login = {
        "claudeAiOauth": {
            "accessToken": ACCESS,
            "refreshToken": REFRESH,
            "expiresAt": int(expires_at * 1000),
            "scopes": ["user:inference"],
            "subscriptionType": "max",
        },
        "mcpOAuth": {"server": {"accessToken": "sk-other"}},
    }
    (claude_home / ".credentials.json").write_text(json.dumps(login))


def describe_a_claude_agent_on_the_host_login() -> None:
    def it_stages_a_home_that_holds_no_real_token(tmp_path: Path) -> None:
        host_login(tmp_path / "claude", time.time() + 3600)
        agent = ClaudeAgent(host_home=tmp_path / "claude")
        home = tmp_path / "home"
        home.mkdir()
        agent.stage_auth(home)
        staged = home / ".claude" / ".credentials.json"
        text = staged.read_text()
        assert ACCESS not in text
        assert REFRESH not in text
        assert "sk-other" not in text
        assert staged.stat().st_mode & 0o777 == 0o600
        oauth = json.loads(text)["claudeAiOauth"]
        assert oauth["expiresAt"] > time.time() * 1000 + 10 * 365 * 86400 * 1000
        assert oauth["subscriptionType"] == "max"

    def it_hands_the_proxy_the_real_token(tmp_path: Path) -> None:
        host_login(tmp_path / "claude", time.time() + 3600)
        agent = ClaudeAgent(host_home=tmp_path / "claude")
        assert isinstance(agent, InjectingAgent)
        assert agent.allow == ()
        assert agent.credential_source is not None
        credential = agent.credential_source.read()
        assert credential.secret == f"Bearer {ACCESS}"
        assert credential.injection.upstream == "api.anthropic.com"
        assert agent.credential_source.env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:41894"

    def it_refuses_a_login_that_has_expired(tmp_path: Path) -> None:
        host_login(tmp_path / "claude", time.time() - 60)
        source = ClaudeAgent(host_home=tmp_path / "claude").credential_source
        assert source is not None
        with pytest.raises(CredentialsExpired, match="expired at"):
            source.read()
