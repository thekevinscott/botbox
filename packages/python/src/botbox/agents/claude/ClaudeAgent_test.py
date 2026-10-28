import json
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import pytest

from botbox.agents.claude.ClaudeAgent import ClaudeAgent

if TYPE_CHECKING:
    from botbox.agents.Agent import Agent
    from botbox.agents.HomeFiles import HomeFiles


class Login:
    """Stands in for `ClaudeLogin`: a placeholder that names the host file it came from."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def placeholder(self) -> str:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        return f"placeholder of {self.path.name}"


class ApiKey:
    """Stands in for `ClaudeApiKey`."""

    placeholder = "placeholder key"

    def __init__(self, key: str) -> None:
        self.key = key


@pytest.fixture(autouse=True)
def collaborators() -> Iterator[None]:
    with (
        patch(f"{__package__}.ClaudeAgent.ClaudeLogin", Login),
        patch(f"{__package__}.ClaudeAgent.ClaudeApiKey", ApiKey),
    ):
        yield


@pytest.fixture
def claude_home(tmp_path: Path) -> Path:
    home = tmp_path / "claude-home"
    home.mkdir()
    (home / ".credentials.json").write_text('{"token": "t"}')
    return home


@pytest.fixture
def agent(claude_home: Path) -> ClaudeAgent:
    return ClaudeAgent(host_home=claude_home)


class Home:
    """Stands in for `HomeFiles`: keeps each write as `HomeFiles.files` does."""

    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, int]] = {}

    def write(self, path: str, content: str | bytes, *, mode: int = 0o644) -> None:
        self.files[path] = (content.encode() if isinstance(content, str) else content, mode)


@pytest.fixture
def home() -> "HomeFiles":
    return cast("HomeFiles", Home())


def describe_the_container() -> None:
    def it_names_its_own_image(agent: ClaudeAgent) -> None:
        assert agent.image == "botbox-claude:latest"

    def it_points_at_its_own_dockerfile(agent: ClaudeAgent) -> None:
        assert agent.dockerfile.parts[-2:] == ("claude", "Dockerfile")

    def it_ships_its_dockerfile_with_the_package(agent: ClaudeAgent) -> None:
        assert agent.dockerfile.read_text().startswith("FROM node:24.20.0-slim\n")

    def it_lives_in_the_users_home(agent: ClaudeAgent) -> None:
        assert agent.home == "/home/user"

    def it_writes_sessions_to_the_projects_directory(agent: ClaudeAgent) -> None:
        assert agent.sessions_dir == ".claude/projects"

    def it_is_an_agent(agent: ClaudeAgent) -> None:
        typed: Agent = agent
        assert typed.home == "/home/user"

    def it_allows_no_host_with_a_login(agent: ClaudeAgent) -> None:
        assert agent.allow == ()

    def it_allows_no_host_with_an_api_key() -> None:
        assert ClaudeAgent(api_key="sk-test").allow == ()

    def it_has_the_proxy_send_the_hosts_login(agent: ClaudeAgent, claude_home: Path) -> None:
        source = agent.credential_source
        assert isinstance(source, Login)
        assert source.path == claude_home / ".credentials.json"

    def it_has_the_proxy_send_the_api_key() -> None:
        source = ClaudeAgent(api_key="sk-test").credential_source
        assert isinstance(source, ApiKey)
        assert source.key == "sk-test"


def describe_host_home() -> None:
    def it_defaults_to_the_users_claude_directory(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        assert ClaudeAgent().host_home == tmp_path / ".claude"

    def it_is_keyword_only(claude_home: Path) -> None:
        with pytest.raises(TypeError):
            ClaudeAgent(None, None, claude_home)  # type: ignore[call-arg, arg-type]


def describe_stage_auth() -> None:
    def it_stages_a_placeholder_login_where_claude_looks_for_one(
        agent: ClaudeAgent, home: "HomeFiles"
    ) -> None:
        agent.stage_auth(home)
        assert home.files[".claude/.credentials.json"][0] == b"placeholder of .credentials.json"

    def it_makes_the_placeholder_readable_by_its_owner_only(
        agent: ClaudeAgent, home: "HomeFiles"
    ) -> None:
        agent.stage_auth(home)
        assert home.files[".claude/.credentials.json"][1] == 0o600

    def it_stages_nothing_else(agent: ClaudeAgent, home: "HomeFiles") -> None:
        agent.stage_auth(home)
        assert list(home.files) == [".claude/.credentials.json"]

    def it_writes_no_file_when_there_is_no_placeholder(
        agent: ClaudeAgent, claude_home: Path, home: "HomeFiles"
    ) -> None:
        (claude_home / ".credentials.json").unlink()
        with pytest.raises(FileNotFoundError):
            agent.stage_auth(home)
        assert home.files == {}

    def it_raises_when_the_host_has_no_credentials(
        agent: ClaudeAgent, claude_home: Path, home: "HomeFiles"
    ) -> None:
        (claude_home / ".credentials.json").unlink()
        with pytest.raises(FileNotFoundError, match=r"\.credentials\.json"):
            agent.stage_auth(home)


def describe_api_key() -> None:
    @pytest.fixture
    def keyed(claude_home: Path) -> ClaudeAgent:
        return ClaudeAgent(api_key="sk-test", host_home=claude_home)

    def it_is_keyword_only() -> None:
        with pytest.raises(TypeError):
            ClaudeAgent(None, None, "sk-test")  # type: ignore[call-arg]

    def it_stages_a_placeholder_key_and_a_helper_that_reads_it(
        keyed: ClaudeAgent, home: "HomeFiles"
    ) -> None:
        keyed.stage_auth(home)
        assert list(home.files) == [".claude/api_key", ".claude/settings.json"]
        assert home.files[".claude/api_key"][0] == b"placeholder key"
        assert json.loads(home.files[".claude/settings.json"][0]) == {
            "apiKeyHelper": "cat /home/user/.claude/api_key"
        }

    def it_makes_the_key_readable_by_its_owner_only(keyed: ClaudeAgent, home: "HomeFiles") -> None:
        keyed.stage_auth(home)
        assert home.files[".claude/api_key"][1] == 0o600

    def it_needs_no_host_credentials(tmp_path: Path, home: "HomeFiles") -> None:
        ClaudeAgent(api_key="sk-test", host_home=tmp_path / "missing").stage_auth(home)
        assert ".claude/api_key" in home.files


def describe_command() -> None:
    def it_runs_claude_in_print_mode_with_json_output_tools_permitted_and_no_mcp() -> None:
        assert ClaudeAgent().command("Fix the tests") == (
            "claude -p 'Fix the tests' --output-format json --dangerously-skip-permissions"
            " --strict-mcp-config"
        )

    def it_shell_quotes_the_prompt() -> None:
        assert ClaudeAgent().command("it's $HOME; rm -rf /") == (
            "claude -p 'it'\"'\"'s $HOME; rm -rf /' --output-format json"
            " --dangerously-skip-permissions --strict-mcp-config"
        )

    def it_passes_the_model_when_set() -> None:
        assert ClaudeAgent(model="claude-opus-5").command("hi") == (
            "claude -p hi --output-format json --dangerously-skip-permissions --strict-mcp-config"
            " --model claude-opus-5"
        )

    def it_passes_the_effort_when_set() -> None:
        assert ClaudeAgent(effort="high").command("hi") == (
            "claude -p hi --output-format json --dangerously-skip-permissions --strict-mcp-config"
            " --effort high"
        )

    def it_passes_both_when_both_are_set() -> None:
        assert ClaudeAgent("claude-opus-5", "high").command("hi") == (
            "claude -p hi --output-format json --dangerously-skip-permissions --strict-mcp-config"
            " --model claude-opus-5 --effort high"
        )

    def it_shell_quotes_the_model_and_effort() -> None:
        assert ClaudeAgent("a b; id", "$(id)").command("hi") == (
            "claude -p hi --output-format json --dangerously-skip-permissions --strict-mcp-config"
            " --model 'a b; id' --effort '$(id)'"
        )


def describe_session() -> None:
    def it_streams_json_both_ways_with_tools_permitted_and_no_mcp() -> None:
        assert ClaudeAgent().session_command() == (
            "claude -p --input-format stream-json --output-format stream-json --verbose"
            " --dangerously-skip-permissions --strict-mcp-config"
        )

    def it_passes_the_model_and_effort_when_set() -> None:
        assert ClaudeAgent("claude-opus-5", "high").session_command() == (
            "claude -p --input-format stream-json --output-format stream-json --verbose"
            " --dangerously-skip-permissions --strict-mcp-config"
            " --model claude-opus-5 --effort high"
        )

    def it_shell_quotes_the_model_and_effort() -> None:
        assert ClaudeAgent("a b; id", "$(id)").session_command() == (
            "claude -p --input-format stream-json --output-format stream-json --verbose"
            " --dangerously-skip-permissions --strict-mcp-config"
            " --model 'a b; id' --effort '$(id)'"
        )

    def it_passes_the_model_alone() -> None:
        assert ClaudeAgent(model="claude-opus-5").session_command() == (
            "claude -p --input-format stream-json --output-format stream-json --verbose"
            " --dangerously-skip-permissions --strict-mcp-config --model claude-opus-5"
        )

    def it_passes_the_effort_alone() -> None:
        assert ClaudeAgent(effort="high").session_command() == (
            "claude -p --input-format stream-json --output-format stream-json --verbose"
            " --dangerously-skip-permissions --strict-mcp-config --effort high"
        )

    def it_encodes_a_message_as_a_user_message() -> None:
        assert json.loads(ClaudeAgent().encode("it's\nhere")) == {
            "type": "user",
            "message": {"role": "user", "content": "it's\nhere"},
        }

    def it_encodes_on_one_line() -> None:
        assert "\n" not in ClaudeAgent().encode("two\nlines")

    def it_ends_the_turn_at_the_result() -> None:
        assert ClaudeAgent().turn_ended({"type": "result", "subtype": "success"}) is True

    def it_compares_the_event_type_by_value() -> None:
        parsed = "".join(["res", "ult"])
        assert ClaudeAgent().turn_ended({"type": parsed}) is True

    def it_keeps_the_turn_open_until_then() -> None:
        agent = ClaudeAgent()
        assert agent.turn_ended({"type": "assistant"}) is False
        assert agent.turn_ended({"type": "system", "subtype": "init"}) is False
        assert agent.turn_ended({}) is False


def describe_tool_timeout() -> None:
    def it_sets_the_bash_timeout_and_turns_off_backgrounding() -> None:
        assert ClaudeAgent(tool_timeout=30).env == {
            "BASH_DEFAULT_TIMEOUT_MS": "30000",
            "BASH_MAX_TIMEOUT_MS": "30000",
            "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
        }

    def it_sets_them_on_the_print_mode_command() -> None:
        assert ClaudeAgent(tool_timeout=30).command("hi") == (
            "BASH_DEFAULT_TIMEOUT_MS=30000 BASH_MAX_TIMEOUT_MS=30000"
            " CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1"
            " claude -p hi --output-format json --dangerously-skip-permissions --strict-mcp-config"
        )

    def it_sets_them_on_the_session_command() -> None:
        assert (
            ClaudeAgent(tool_timeout=30)
            .session_command()
            .startswith(
                "BASH_DEFAULT_TIMEOUT_MS=30000 BASH_MAX_TIMEOUT_MS=30000"
                " CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1 claude -p --input-format stream-json "
            )
        )

    def it_rounds_a_fraction_of_a_millisecond_up() -> None:
        assert ClaudeAgent(tool_timeout=0.0001).env["BASH_MAX_TIMEOUT_MS"] == "1"

    def it_sets_nothing_at_0() -> None:
        assert ClaudeAgent(tool_timeout=0).env == {}
        assert ClaudeAgent(tool_timeout=0).command("hi").startswith("claude -p ")

    def it_rejects_a_negative_limit() -> None:
        with pytest.raises(ValueError, match="tool_timeout is in seconds"):
            ClaudeAgent(tool_timeout=-1)
