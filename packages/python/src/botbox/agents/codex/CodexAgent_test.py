import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import pytest

from botbox.agents.codex.CodexAgent import CodexAgent

if TYPE_CHECKING:
    from botbox.agents.Agent import Agent
    from botbox.agents.HomeFiles import HomeFiles

MODULE = f"{__package__}.CodexAgent"


class Login:
    """Stands in for `CodexLogin`: a placeholder that names the host file it came from."""

    base_url = "http://proxy/backend-api/codex"

    def __init__(self, path: Path) -> None:
        self.path = path

    def placeholder(self) -> str:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        return f"placeholder of {self.path.name}"


class ApiKey:
    """Stands in for `CodexApiKey`."""

    base_url = "http://proxy/v1"

    def __init__(self, key: str) -> None:
        self.key = key

    def placeholder(self) -> str:
        return "placeholder key"


@pytest.fixture(autouse=True)
def collaborators() -> Iterator[None]:
    with (
        patch(f"{MODULE}.CodexLogin", Login),
        patch(f"{MODULE}.CodexApiKey", ApiKey),
        patch(f"{MODULE}.PROXY_URL", "http://proxy"),
    ):
        yield


@pytest.fixture
def codex_home(tmp_path: Path) -> Path:
    home = tmp_path / "codex-home"
    home.mkdir()
    (home / "auth.json").write_text('{"auth_mode": "chatgpt"}')
    return home


@pytest.fixture
def agent(codex_home: Path) -> CodexAgent:
    return CodexAgent(host_home=codex_home)


class Home:
    """Stands in for `HomeFiles`: keeps each write as `HomeFiles.files` does."""

    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, int]] = {}

    def write(self, path: str, content: str | bytes, *, mode: int = 0o644) -> None:
        self.files[path] = (content.encode() if isinstance(content, str) else content, mode)


@pytest.fixture
def home() -> "HomeFiles":
    return cast("HomeFiles", Home())


def staged(home: "HomeFiles") -> str:
    return home.files[".codex/auth.json"][0].decode()


def config(home: "HomeFiles") -> dict[str, object]:
    return tomllib.loads(home.files[".codex/config.toml"][0].decode())


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

    def it_allows_no_host_on_a_chatgpt_login(agent: CodexAgent) -> None:
        assert agent.allow == ()

    def it_allows_no_host_with_a_key() -> None:
        assert CodexAgent(api_key="k").allow == ()

    def it_satisfies_the_agent_protocol(agent: CodexAgent) -> None:
        typed: Agent = agent
        assert typed.allow == ()


def describe_credential_source() -> None:
    def it_is_the_host_login(agent: CodexAgent, codex_home: Path) -> None:
        source = agent.credential_source
        assert isinstance(source, Login)
        assert source.path == codex_home / "auth.json"

    def it_is_the_key_when_given() -> None:
        source = CodexAgent(api_key="sk-test").credential_source
        assert isinstance(source, ApiKey)
        assert source.key == "sk-test"


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
    def it_stages_the_login_and_config_where_codex_looks(
        agent: CodexAgent, home: "HomeFiles"
    ) -> None:
        agent.stage_auth(home)
        assert list(home.files) == [".codex/auth.json", ".codex/config.toml"]

    def it_stages_a_placeholder_of_the_host_login(agent: CodexAgent, home: "HomeFiles") -> None:
        agent.stage_auth(home)
        assert staged(home) == "placeholder of auth.json"

    def it_makes_the_login_readable_by_its_owner_only(agent: CodexAgent, home: "HomeFiles") -> None:
        agent.stage_auth(home)
        assert home.files[".codex/auth.json"][1] == 0o600

    def it_points_codex_at_the_proxy(agent: CodexAgent, home: "HomeFiles") -> None:
        agent.stage_auth(home)
        assert config(home) == {
            "model_provider": "botbox",
            "chatgpt_base_url": "http://proxy/backend-api/",
            "model_providers": {
                "botbox": {
                    "name": "botbox",
                    "base_url": "http://proxy/backend-api/codex",
                    "wire_api": "responses",
                    "requires_openai_auth": True,
                }
            },
        }

    def it_raises_when_the_host_has_no_login(
        agent: CodexAgent, codex_home: Path, home: "HomeFiles"
    ) -> None:
        (codex_home / "auth.json").unlink()
        with pytest.raises(FileNotFoundError, match=r"auth\.json"):
            agent.stage_auth(home)
        assert home.files == {}


def describe_api_key() -> None:
    @pytest.fixture
    def keyed(tmp_path: Path) -> CodexAgent:
        return CodexAgent(api_key="sk-test", host_home=tmp_path / "missing")

    def it_is_keyword_only() -> None:
        with pytest.raises(TypeError):
            CodexAgent(None, None, "sk-test")  # type: ignore[call-arg]

    def it_stages_a_placeholder_key(keyed: CodexAgent, home: "HomeFiles") -> None:
        keyed.stage_auth(home)
        assert staged(home) == "placeholder key"

    def it_points_codex_at_the_proxys_api(keyed: CodexAgent, home: "HomeFiles") -> None:
        keyed.stage_auth(home)
        provider = config(home)["model_providers"]
        assert provider == {
            "botbox": {
                "name": "botbox",
                "base_url": "http://proxy/v1",
                "wire_api": "responses",
                "requires_openai_auth": True,
            }
        }

    def it_keeps_the_key_out_of_the_command(keyed: CodexAgent) -> None:
        assert "sk-test" not in keyed.command("hi")

    def it_keeps_the_key_out_of_the_repr(keyed: CodexAgent) -> None:
        assert "sk-test" not in repr(keyed)


def describe_command() -> None:
    def it_runs_codex_exec_with_json_output_and_no_sandbox_of_its_own() -> None:
        assert CodexAgent().command("Fix the tests") == (
            "codex exec --json --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check"
            " --disable plugins --disable apps --config analytics.enabled=false 'Fix the tests'"
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
    def it_has_no_session_command() -> None:
        with pytest.raises(
            NotImplementedError,
            match=r"^NOT IMPLEMENTED: CodexAgent has no session mode\.$",
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
