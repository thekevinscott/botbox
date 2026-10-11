from pathlib import Path

import pytest

from botbox.agents.ClaudeAgent import ClaudeAgent


@pytest.fixture
def claude_home(tmp_path: Path) -> Path:
    home = tmp_path / "claude-home"
    home.mkdir()
    (home / ".credentials.json").write_text('{"token": "t"}')
    return home


@pytest.fixture
def agent(claude_home: Path) -> ClaudeAgent:
    return ClaudeAgent(host_home=claude_home)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    staged = tmp_path / "home"
    staged.mkdir()
    return staged


def describe_the_container() -> None:
    def it_names_its_own_image(agent: ClaudeAgent) -> None:
        assert agent.image == "botbox-claude:latest"

    def it_points_at_its_own_dockerfile(agent: ClaudeAgent) -> None:
        assert agent.dockerfile.name == "claude.Dockerfile"

    def it_ships_its_dockerfile_with_the_package(agent: ClaudeAgent) -> None:
        assert agent.dockerfile.read_text().startswith("FROM node:24.20.0-slim\n")

    def it_lives_in_the_node_users_home(agent: ClaudeAgent) -> None:
        assert agent.home == "/home/node"

    def it_finds_transcripts_under_the_projects_directory(agent: ClaudeAgent) -> None:
        assert agent.transcripts == ".claude/projects/**/*.jsonl"

    def it_allows_only_the_anthropic_api(agent: ClaudeAgent) -> None:
        assert agent.allow == ("api.anthropic.com",)


def describe_host_home() -> None:
    def it_defaults_to_the_users_claude_directory(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        assert ClaudeAgent().host_home == tmp_path / ".claude"

    def it_is_keyword_only(claude_home: Path) -> None:
        with pytest.raises(TypeError):
            ClaudeAgent(claude_home)  # type: ignore[call-arg]


def describe_stage_auth() -> None:
    def it_stages_the_credentials_where_claude_looks_for_them(
        agent: ClaudeAgent, home: Path
    ) -> None:
        agent.stage_auth(home)
        assert (home / ".claude" / ".credentials.json").read_text() == '{"token": "t"}'

    def it_stages_nothing_else(agent: ClaudeAgent, home: Path) -> None:
        agent.stage_auth(home)
        assert [p.relative_to(home).as_posix() for p in sorted(home.rglob("*"))] == [
            ".claude",
            ".claude/.credentials.json",
        ]

    def it_copies_rather_than_shares_the_host_file(
        agent: ClaudeAgent, claude_home: Path, home: Path
    ) -> None:
        agent.stage_auth(home)
        copy = home / ".claude" / ".credentials.json"
        assert copy.stat().st_ino != (claude_home / ".credentials.json").stat().st_ino

    def it_leaves_the_host_file_untouched_when_the_container_rewrites_it(
        agent: ClaudeAgent, claude_home: Path, home: Path
    ) -> None:
        agent.stage_auth(home)
        (home / ".claude" / ".credentials.json").write_text('{"token": "refreshed"}')
        assert (claude_home / ".credentials.json").read_text() == '{"token": "t"}'

    def it_raises_when_the_host_has_no_credentials(
        agent: ClaudeAgent, claude_home: Path, home: Path
    ) -> None:
        (claude_home / ".credentials.json").unlink()
        with pytest.raises(FileNotFoundError, match=r"\.credentials\.json"):
            agent.stage_auth(home)
