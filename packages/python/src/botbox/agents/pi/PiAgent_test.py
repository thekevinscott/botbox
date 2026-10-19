import json
from pathlib import Path

import pytest

from botbox.agents.pi.PiAgent import PiAgent


@pytest.fixture
def pi_home(tmp_path: Path) -> Path:
    home = tmp_path / "pi-home"
    home.mkdir()
    (home / "auth.json").write_text('{"key": "k"}')
    (home / "models.json").write_text('{"providers": []}')
    return home


@pytest.fixture
def agent(pi_home: Path) -> PiAgent:
    return PiAgent(provider="openrouter", host_home=pi_home)


@pytest.fixture
def local_host(monkeypatch: pytest.MonkeyPatch) -> str:
    host = "model-host.example"
    monkeypatch.setenv("PI_AGENT_HOST", host)
    return host


@pytest.fixture
def home(tmp_path: Path) -> Path:
    staged = tmp_path / "home"
    staged.mkdir()
    return staged


def describe_the_container() -> None:
    def it_names_its_own_image(agent: PiAgent) -> None:
        assert agent.image == "botbox-pi:latest"

    def it_points_at_its_own_dockerfile(agent: PiAgent) -> None:
        assert agent.dockerfile.parts[-2:] == ("pi", "Dockerfile")

    def it_ships_its_dockerfile_with_the_package(agent: PiAgent) -> None:
        assert agent.dockerfile.read_text().startswith("FROM node:24.20.0-slim\n")

    def it_lives_in_the_users_home(agent: PiAgent) -> None:
        assert agent.home == "/home/user"

    def it_finds_transcripts_under_the_sessions_directory(agent: PiAgent) -> None:
        assert agent.transcripts == ".pi/agent/sessions/**/*.jsonl"


def describe_host_home() -> None:
    def it_defaults_to_the_users_pi_agent_directory(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        assert PiAgent(provider="openrouter").host_home == tmp_path / ".pi" / "agent"


def describe_the_provider() -> None:
    def it_is_required() -> None:
        with pytest.raises(TypeError):
            PiAgent()  # type: ignore[call-arg]

    def it_allows_the_host_openrouter_answers_on() -> None:
        assert PiAgent(provider="openrouter").allow == ("openrouter.ai",)

    def it_allows_the_host_the_local_model_serves_from(local_host: str) -> None:
        assert PiAgent(provider="tower").allow == (local_host,)

    def it_refuses_a_local_provider_with_no_host_configured(
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("PI_AGENT_HOST", raising=False)
        with pytest.raises(ValueError, match="PI_AGENT_HOST"):
            PiAgent(provider="tower")

    def it_rejects_a_provider_it_has_no_allowlist_for() -> None:
        with pytest.raises(ValueError, match="anthropic"):
            PiAgent(provider="anthropic")

    def it_lists_the_providers_it_knows() -> None:
        with pytest.raises(ValueError, match="openrouter, tower"):
            PiAgent(provider="")


def describe_stage_auth() -> None:
    def it_stages_the_key_and_the_provider_catalogue_where_pi_looks(
        agent: PiAgent, home: Path
    ) -> None:
        agent.stage_auth(home)
        assert [p.relative_to(home).as_posix() for p in sorted(home.rglob("*"))] == [
            ".pi",
            ".pi/agent",
            ".pi/agent/auth.json",
            ".pi/agent/models.json",
        ]

    def it_copies_rather_than_shares_the_host_files(
        agent: PiAgent, pi_home: Path, home: Path
    ) -> None:
        agent.stage_auth(home)
        copy = home / ".pi" / "agent" / "auth.json"
        assert copy.read_text() == '{"key": "k"}'
        assert copy.stat().st_ino != (pi_home / "auth.json").stat().st_ino

    def it_raises_when_the_host_has_no_key(agent: PiAgent, pi_home: Path, home: Path) -> None:
        (pi_home / "auth.json").unlink()
        with pytest.raises(FileNotFoundError, match=r"auth\.json"):
            agent.stage_auth(home)

    def it_stages_only_the_key_when_the_host_has_no_provider_catalogue(
        agent: PiAgent, pi_home: Path, home: Path
    ) -> None:
        (pi_home / "models.json").unlink()
        agent.stage_auth(home)
        assert [p.relative_to(home).as_posix() for p in sorted(home.rglob("*"))] == [
            ".pi",
            ".pi/agent",
            ".pi/agent/auth.json",
        ]


def describe_api_key() -> None:
    @pytest.fixture
    def keyed(pi_home: Path) -> PiAgent:
        return PiAgent(provider="openrouter", api_key="sk-or-test", host_home=pi_home)

    def it_is_keyword_only() -> None:
        with pytest.raises(TypeError):
            PiAgent("openrouter", None, "sk-or-test")  # type: ignore[call-arg]

    def it_stages_the_key_for_the_provider_alone(keyed: PiAgent, home: Path) -> None:
        keyed.stage_auth(home)
        assert [p.relative_to(home).as_posix() for p in sorted(home.rglob("*"))] == [
            ".pi",
            ".pi/agent",
            ".pi/agent/auth.json",
        ]
        assert json.loads((home / ".pi" / "agent" / "auth.json").read_text()) == {
            "openrouter": {"type": "api_key", "key": "sk-or-test"}
        }

    def it_makes_the_key_readable_by_its_owner_only(keyed: PiAgent, home: Path) -> None:
        keyed.stage_auth(home)
        assert (home / ".pi" / "agent" / "auth.json").stat().st_mode & 0o777 == 0o600

    def it_needs_no_host_files(tmp_path: Path, home: Path) -> None:
        PiAgent("openrouter", api_key="sk-or-test", host_home=tmp_path / "missing").stage_auth(home)
        assert (home / ".pi" / "agent" / "auth.json").exists()

    def it_keeps_the_key_out_of_the_command(keyed: PiAgent) -> None:
        assert "sk-or-test" not in keyed.command("hi")

    def it_keeps_the_key_out_of_the_repr(keyed: PiAgent) -> None:
        assert "sk-or-test" not in repr(keyed)


def describe_command() -> None:
    def it_runs_pi_in_print_mode_with_json_output_against_the_provider() -> None:
        assert PiAgent(provider="openrouter").command("Fix the tests") == (
            "pi -p 'Fix the tests' --mode json --provider openrouter"
        )

    def it_shell_quotes_the_prompt() -> None:
        assert PiAgent(provider="openrouter").command("it's $HOME") == (
            "pi -p 'it'\"'\"'s $HOME' --mode json --provider openrouter"
        )

    def it_passes_the_model_when_set() -> None:
        assert PiAgent("openrouter", "qwen/qwen3-coder").command("hi") == (
            "pi -p hi --mode json --provider openrouter --model qwen/qwen3-coder"
        )

    def it_takes_the_model_by_keyword() -> None:
        assert PiAgent(provider="openrouter", model="m").command("hi").endswith(" --model m")
