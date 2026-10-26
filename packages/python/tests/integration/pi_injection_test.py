"""PiAgent on OpenRouter: the box's home gets a placeholder, the proxy gets the key."""

import json
from pathlib import Path

import pytest

from botbox import InjectingAgent, PiAgent

HOST_KEY = "sk-or-v1-host-key"
OTHER_KEY = "sk-ant-other-key"


@pytest.fixture
def pi_home(tmp_path: Path) -> Path:
    home = tmp_path / "pi"
    home.mkdir()
    auth = {
        "openrouter": {"type": "api_key", "key": HOST_KEY},
        "anthropic": {"type": "api_key", "key": OTHER_KEY},
    }
    (home / "auth.json").write_text(json.dumps(auth))
    models = {
        "providers": {
            "openrouter": {"apiKey": HOST_KEY, "headers": {"X-Key": HOST_KEY}, "api": "x"},
            "ollama": {"baseUrl": "http://models.example/v1", "apiKey": OTHER_KEY},
        }
    }
    (home / "models.json").write_text(json.dumps(models))
    return home


@pytest.fixture
def home(tmp_path: Path) -> Path:
    staged = tmp_path / "home"
    staged.mkdir()
    return staged


def describe_a_pi_agent_on_openrouter() -> None:
    def it_stages_a_home_that_holds_no_real_key(pi_home: Path, home: Path) -> None:
        PiAgent("openrouter", host_home=pi_home).stage_auth(home)
        staged = home / ".pi" / "agent"
        for name in ("auth.json", "models.json"):
            text = (staged / name).read_text()
            assert HOST_KEY not in text
            assert OTHER_KEY not in text
        assert (staged / "auth.json").stat().st_mode & 0o777 == 0o600
        assert json.loads((staged / "models.json").read_text()) == {
            "providers": {"openrouter": {"api": "x", "baseUrl": "http://127.0.0.1:41894/api/v1"}}
        }

    def it_hands_the_proxy_the_hosts_key(pi_home: Path) -> None:
        agent = PiAgent("openrouter", host_home=pi_home)
        assert isinstance(agent, InjectingAgent)
        assert agent.allow == ()
        assert agent.credential_source is not None
        credential = agent.credential_source.read()
        assert credential.secret == f"Bearer {HOST_KEY}"
        assert credential.injection.upstream == "openrouter.ai"
        assert credential.injection.paths == "/api/v1/chat/completions"
        assert credential.injection.methods == ("POST",)

    def it_hands_the_proxy_a_given_key(tmp_path: Path, home: Path) -> None:
        agent = PiAgent("openrouter", api_key="sk-or-v1-given", host_home=tmp_path / "missing")
        assert agent.credential_source is not None
        assert agent.credential_source.read().secret == "Bearer sk-or-v1-given"
        agent.stage_auth(home)
        assert "sk-or-v1-given" not in (home / ".pi" / "agent" / "auth.json").read_text()

    def it_refuses_a_host_key_that_is_a_command(pi_home: Path) -> None:
        (pi_home / "auth.json").write_text(
            json.dumps({"openrouter": {"type": "api_key", "key": "!op read op://k"}})
        )
        source = PiAgent("openrouter", host_home=pi_home).credential_source
        assert source is not None
        with pytest.raises(ValueError, match="literal key"):
            source.read()


def describe_a_pi_agent_on_a_custom_provider() -> None:
    def it_injects_nothing_and_copies_the_host_files(pi_home: Path, home: Path) -> None:
        agent = PiAgent("ollama", host_home=pi_home)
        assert agent.credential_source is None
        assert agent.allow == ("models.example",)
        agent.stage_auth(home)
        staged = home / ".pi" / "agent"
        assert (staged / "auth.json").read_text() == (pi_home / "auth.json").read_text()
