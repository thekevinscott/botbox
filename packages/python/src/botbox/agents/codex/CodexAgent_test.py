import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from botbox.agents.codex.CodexAgent import CodexAgent

if TYPE_CHECKING:
    from botbox.agents.agent import Agent


@pytest.fixture
def codex_home(tmp_path: Path) -> Path:
    home = tmp_path / "codex-home"
    home.mkdir()
    (home / "auth.json").write_text('{"auth_mode": "chatgpt"}')
    return home


@pytest.fixture
def agent(codex_home: Path) -> CodexAgent:
    return CodexAgent(host_home=codex_home)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    staged = tmp_path / "home"
    staged.mkdir()
    return staged


def staged(home: Path) -> dict[str, object]:
    login: dict[str, object] = json.loads((home / ".codex" / "auth.json").read_text())
    return login


def describe_the_container() -> None:
    def it_names_its_own_image(agent: CodexAgent) -> None:
        assert agent.image == "botbox-codex:latest"

    def it_points_at_its_own_dockerfile(agent: CodexAgent) -> None:
        assert agent.dockerfile.parts[-2:] == ("codex", "Dockerfile")

    def it_ships_its_dockerfile_with_the_package(agent: CodexAgent) -> None:
        assert agent.dockerfile.read_text().startswith("FROM node:24.20.0-slim\n")

    def it_lives_in_the_users_home(agent: CodexAgent) -> None:
        assert agent.home == "/home/user"

    def it_writes_sessions_to_the_sessions_directory(agent: CodexAgent) -> None:
        assert agent.sessions_dir == ".codex/sessions"

    def it_allows_only_chatgpt_on_a_chatgpt_login(agent: CodexAgent) -> None:
        assert agent.allow == ("chatgpt.com",)

    def it_allows_only_the_openai_api_with_a_key() -> None:
        assert CodexAgent(api_key="k").allow == ("api.openai.com",)

    def it_satisfies_the_agent_protocol(agent: CodexAgent) -> None:
        typed: Agent = agent
        assert typed.allow == ("chatgpt.com",)


def describe_host_home() -> None:
    def it_defaults_to_the_users_codex_directory(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        assert CodexAgent().host_home == tmp_path / ".codex"

    def it_is_keyword_only(codex_home: Path) -> None:
        with pytest.raises(TypeError):
            CodexAgent(None, None, None, codex_home)  # type: ignore[call-arg]


def describe_stage_auth() -> None:
    def it_stages_the_login_where_codex_looks(agent: CodexAgent, home: Path) -> None:
        agent.stage_auth(home)
        assert [p.relative_to(home).as_posix() for p in sorted(home.rglob("*"))] == [
            ".codex",
            ".codex/auth.json",
        ]

    def it_copies_rather_than_shares_the_host_login(
        agent: CodexAgent, codex_home: Path, home: Path
    ) -> None:
        agent.stage_auth(home)
        copy = home / ".codex" / "auth.json"
        assert copy.read_text() == '{"auth_mode": "chatgpt"}'
        assert copy.stat().st_ino != (codex_home / "auth.json").stat().st_ino

    def it_raises_when_the_host_has_no_login(
        agent: CodexAgent, codex_home: Path, home: Path
    ) -> None:
        (codex_home / "auth.json").unlink()
        with pytest.raises(FileNotFoundError, match=r"auth\.json"):
            agent.stage_auth(home)


def describe_api_key() -> None:
    @pytest.fixture
    def keyed(tmp_path: Path) -> CodexAgent:
        return CodexAgent(api_key="sk-test", host_home=tmp_path / "missing")

    def it_is_keyword_only() -> None:
        with pytest.raises(TypeError):
            CodexAgent(None, None, "sk-test")  # type: ignore[call-arg]

    def it_stages_the_key_in_api_key_mode(keyed: CodexAgent, home: Path) -> None:
        keyed.stage_auth(home)
        assert staged(home) == {"auth_mode": "apikey", "OPENAI_API_KEY": "sk-test"}

    def it_makes_the_key_readable_by_its_owner_only(keyed: CodexAgent, home: Path) -> None:
        keyed.stage_auth(home)
        assert (home / ".codex" / "auth.json").stat().st_mode & 0o777 == 0o600

    def it_keeps_the_key_out_of_the_command(keyed: CodexAgent) -> None:
        assert "sk-test" not in keyed.command("hi")

    def it_keeps_the_key_out_of_the_repr(keyed: CodexAgent) -> None:
        assert "sk-test" not in repr(keyed)


def describe_command() -> None:
    def it_runs_codex_exec_with_json_output_and_no_sandbox_of_its_own() -> None:
        assert CodexAgent().command("Fix the tests") == (
            "codex exec --json --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check"
            " --disable plugins --config analytics.enabled=false 'Fix the tests'"
        )

    def it_shell_quotes_the_prompt() -> None:
        assert CodexAgent().command("it's $HOME").endswith(" 'it'\"'\"'s $HOME'")

    def it_passes_the_model_when_set() -> None:
        assert CodexAgent("gpt-5.5").command("hi").endswith(" --model gpt-5.5 hi")

    def it_passes_the_effort_when_set() -> None:
        assert (
            CodexAgent(effort="low")
            .command("hi")
            .endswith(" --config model_reasoning_effort=low hi")
        )

    def it_shell_quotes_the_model_and_effort() -> None:
        assert (
            CodexAgent("a b; id", "$(id)")
            .command("hi")
            .endswith(" --model 'a b; id' --config 'model_reasoning_effort=$(id)' hi")
        )


def describe_session() -> None:
    def it_has_no_session_command_and_points_at_pi() -> None:
        with pytest.raises(
            NotImplementedError,
            match=r"^NOT IMPLEMENTED: CodexAgent has no session mode\. For a Codex model in a"
            r" session, use PiAgent\('openrouter', 'openai/<model>'\)\.$",
        ):
            CodexAgent().session_command()

    def it_encodes_nothing() -> None:
        with pytest.raises(NotImplementedError, match="NOT IMPLEMENTED"):
            CodexAgent().encode("hi")

    def it_ends_no_turn() -> None:
        with pytest.raises(NotImplementedError, match="NOT IMPLEMENTED"):
            CodexAgent().turn_ended({"type": "turn/completed"})


def describe_tool_timeout() -> None:
    def it_accepts_no_limit() -> None:
        CodexAgent(tool_timeout=0)

    def it_raises_on_a_limit_it_cannot_enforce() -> None:
        with pytest.raises(
            NotImplementedError,
            match=r"^NOT IMPLEMENTED: CodexAgent has no tool_timeout\.",
        ):
            CodexAgent(tool_timeout=30)

    def it_rejects_a_negative_limit() -> None:
        with pytest.raises(ValueError, match="tool_timeout is in seconds"):
            CodexAgent(tool_timeout=-1)
