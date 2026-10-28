"""ClaudeAgent on an API key: the box's home gets a placeholder, the proxy gets the key."""

import json
from pathlib import Path

from staged_home_test import staged_home

from botbox import ClaudeAgent
from botbox.credential_proxy import envoy_config

KEY = "sk-ant-api03-host-key"


def describe_a_claude_agent_on_an_api_key() -> None:
    def it_stages_a_home_that_holds_no_real_key(tmp_path: Path) -> None:
        agent = ClaudeAgent(api_key=KEY, host_home=tmp_path / "missing")
        home = staged_home(agent, tmp_path / "home")
        staged = home / ".claude" / "api_key"
        assert staged.read_text() == "sk-ant-api03-botbox-placeholder"
        assert staged.stat().st_mode & 0o777 == 0o600
        assert not any(KEY in p.read_text() for p in home.rglob("*") if p.is_file())

    def it_hands_the_proxy_the_real_key(tmp_path: Path) -> None:
        agent = ClaudeAgent(api_key=KEY, host_home=tmp_path / "missing")
        assert agent.credential_source is not None
        assert agent.allow == ()
        credential = agent.credential_source.read()
        assert credential.secret == KEY
        assert agent.credential_source.env == {"ANTHROPIC_BASE_URL": "http://127.0.0.1:41894"}

    def it_has_envoy_set_x_api_key_and_drop_the_bearer(tmp_path: Path) -> None:
        agent = ClaudeAgent(api_key=KEY, host_home=tmp_path / "missing")
        config = envoy_config(agent.credential_source.read().injection, "/sockets/c.sock")
        text = json.dumps(json.loads(config))
        assert '"header": "x-api-key"' in text
        assert '"request_headers_to_remove": ["Authorization"]' in text
        assert KEY not in config
