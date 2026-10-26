import json
import shlex
from pathlib import Path

import pytest

from botbox.agents.pi.PiAgent import PiAgent, drop_updates


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
def custom_home(tmp_path: Path) -> Path:
    home = tmp_path / "custom-home"
    home.mkdir()
    (home / "auth.json").write_text("{}")
    (home / "models.json").write_text(
        json.dumps({"providers": {"ollama": {"baseUrl": "http://models.example:11434/v1"}}})
    )
    return home


@pytest.fixture
def models_home(custom_home: Path) -> Path:
    (custom_home / "models.json").write_text(
        json.dumps(
            {
                "providers": {
                    "ollama": {
                        "baseUrl": "https://default.example/v1",
                        "models": [
                            {"id": "special", "baseUrl": "https://special.example/v1"},
                            {"id": "plain"},
                        ],
                    }
                }
            }
        )
    )
    return custom_home


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

    def it_copies_the_tool_timeout_extension_into_the_image(agent: PiAgent) -> None:
        assert "tool_call" in agent.dockerfile.with_name("tool-timeout.ts").read_text()
        assert (
            "COPY tool-timeout.ts /usr/local/lib/botbox/tool-timeout.ts\n"
            in agent.dockerfile.read_text()
        )

    def it_lives_in_the_users_home(agent: PiAgent) -> None:
        assert agent.home == "/home/user"

    def it_writes_sessions_to_the_sessions_directory(agent: PiAgent) -> None:
        assert agent.sessions_dir == ".pi/agent/sessions"


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

    def it_allows_the_host_of_a_custom_providers_base_url(custom_home: Path) -> None:
        assert PiAgent("ollama", host_home=custom_home).allow == ("models.example",)

    def it_reads_models_json_with_comments_and_trailing_commas(custom_home: Path) -> None:
        (custom_home / "models.json").write_text(
            '// providers\n{"providers": {"ollama": {\n'
            '  /* local */ "baseUrl": "https://models.example/v1",\n},},}\n'
        )
        assert PiAgent("ollama", host_home=custom_home).allow == ("models.example",)

    def it_allows_the_host_of_the_selected_models_own_base_url(models_home: Path) -> None:
        assert PiAgent("ollama", "special", host_home=models_home).allow == ("special.example",)

    def it_falls_back_to_the_providers_base_url_for_a_model_without_one(
        models_home: Path,
    ) -> None:
        assert PiAgent("ollama", "plain", host_home=models_home).allow == ("default.example",)

    def it_falls_back_to_the_providers_base_url_for_an_undefined_model(
        models_home: Path,
    ) -> None:
        assert PiAgent("ollama", "other", host_home=models_home).allow == ("default.example",)

    def it_allows_every_host_the_provider_may_use_when_no_model_is_set(
        models_home: Path,
    ) -> None:
        assert PiAgent("ollama", host_home=models_home).allow == (
            "default.example",
            "special.example",
        )

    def it_takes_the_host_from_the_model_when_the_provider_has_no_base_url(
        models_home: Path,
    ) -> None:
        (models_home / "models.json").write_text(
            json.dumps(
                {
                    "providers": {
                        "ollama": {
                            "models": [{"id": "special", "baseUrl": "https://special.example"}]
                        }
                    }
                }
            )
        )
        assert PiAgent("ollama", "special", host_home=models_home).allow == ("special.example",)

    def it_refuses_a_provider_missing_from_models_json(custom_home: Path) -> None:
        with pytest.raises(ValueError, match=r"'vllm'.*models\.json"):
            PiAgent("vllm", host_home=custom_home)

    def it_refuses_a_custom_provider_with_no_base_url(custom_home: Path) -> None:
        (custom_home / "models.json").write_text(json.dumps({"providers": {"ollama": {}}}))
        with pytest.raises(ValueError, match="baseUrl"):
            PiAgent("ollama", host_home=custom_home)

    def it_refuses_a_custom_provider_when_there_is_no_models_json(tmp_path: Path) -> None:
        with pytest.raises(ValueError, match=r"'ollama'.*models\.json"):
            PiAgent("ollama", host_home=tmp_path)

    def it_refuses_a_custom_provider_with_an_api_key(custom_home: Path) -> None:
        with pytest.raises(ValueError, match="api_key"):
            PiAgent("ollama", api_key="k", host_home=custom_home)


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


def describe_drop_updates() -> None:
    def it_pipes_the_command_through_an_unbuffered_sed_under_pipefail() -> None:
        assert shlex.split(drop_updates("pi --mode rpc")) == [
            "exec",
            "bash",
            "-o",
            "pipefail",
            "-c",
            'pi --mode rpc | sed -u -e \'/^{"type":"message_update"/d\''
            ' -e \'/^{"type":"tool_execution_update"/d\'',
        ]


def describe_command() -> None:
    def it_runs_pi_in_print_mode_with_json_output_against_the_provider() -> None:
        assert PiAgent(provider="openrouter").command("Fix the tests") == drop_updates(
            "pi -p 'Fix the tests' --mode json --provider openrouter"
        )

    def it_passes_a_custom_provider_through(custom_home: Path) -> None:
        assert PiAgent("ollama", host_home=custom_home).command("hi") == drop_updates(
            "pi -p hi --mode json --provider ollama"
        )

    def it_shell_quotes_the_provider(tmp_path: Path) -> None:
        (tmp_path / "models.json").write_text(
            json.dumps({"providers": {"a b; id": {"baseUrl": "https://models.example"}}})
        )
        agent = PiAgent("a b; id", host_home=tmp_path)
        assert agent.command("hi") == drop_updates("pi -p hi --mode json --provider 'a b; id'")
        assert agent.session_command() == drop_updates("pi --mode rpc --provider 'a b; id'")

    def it_shell_quotes_the_prompt() -> None:
        assert PiAgent(provider="openrouter").command("it's $HOME") == drop_updates(
            "pi -p 'it'\"'\"'s $HOME' --mode json --provider openrouter"
        )

    def it_passes_the_model_when_set() -> None:
        assert PiAgent("openrouter", "qwen/qwen3-coder").command("hi") == drop_updates(
            "pi -p hi --mode json --provider openrouter --model qwen/qwen3-coder"
        )

    def it_takes_the_model_by_keyword() -> None:
        assert PiAgent(provider="openrouter", model="m").command("hi") == drop_updates(
            "pi -p hi --mode json --provider openrouter --model m"
        )

    def it_shell_quotes_the_model() -> None:
        assert PiAgent("openrouter", "a b; id").command("hi") == drop_updates(
            "pi -p hi --mode json --provider openrouter --model 'a b; id'"
        )


def describe_tool_timeout() -> None:
    def it_loads_the_extension_with_the_limit_in_print_mode() -> None:
        assert PiAgent("openrouter", tool_timeout=30).command("hi") == drop_updates(
            "BOTBOX_TOOL_TIMEOUT=30 pi -p hi --mode json --provider openrouter"
            " -e /usr/local/lib/botbox/tool-timeout.ts"
        )

    def it_loads_the_extension_with_the_limit_in_session_mode() -> None:
        assert PiAgent("openrouter", "m", tool_timeout=2.5).session_command() == drop_updates(
            "BOTBOX_TOOL_TIMEOUT=2.5 pi --mode rpc --provider openrouter --model m"
            " -e /usr/local/lib/botbox/tool-timeout.ts"
        )

    def it_sets_nothing_when_zero() -> None:
        agent = PiAgent("openrouter", tool_timeout=0)
        assert "tool-timeout" not in agent.command("hi") + agent.session_command()

    def it_rejects_a_negative_timeout() -> None:
        with pytest.raises(ValueError, match="tool_timeout is in seconds and must be 0 or more"):
            PiAgent("openrouter", tool_timeout=-1)


def describe_session() -> None:
    def it_runs_pi_in_rpc_mode_against_the_provider() -> None:
        assert PiAgent("openrouter").session_command() == drop_updates(
            "pi --mode rpc --provider openrouter"
        )

    def it_passes_the_model_when_set() -> None:
        assert PiAgent("openrouter", "qwen/qwen3-coder").session_command() == drop_updates(
            "pi --mode rpc --provider openrouter --model qwen/qwen3-coder"
        )

    def it_shell_quotes_the_model() -> None:
        assert PiAgent("openrouter", "a b; id").session_command() == drop_updates(
            "pi --mode rpc --provider openrouter --model 'a b; id'"
        )

    def it_encodes_a_message_as_a_prompt_command() -> None:
        assert json.loads(PiAgent("openrouter").encode("it's\nhere")) == {
            "type": "prompt",
            "message": "it's\nhere",
        }

    def it_encodes_on_one_line() -> None:
        assert "\n" not in PiAgent("openrouter").encode("two\nlines")

    def it_ends_the_turn_when_the_agent_ends() -> None:
        assert PiAgent("openrouter").turn_ended({"type": "agent_end", "messages": []}) is True

    def it_compares_the_event_type_by_value() -> None:
        parsed = "".join(["agent", "_end"])
        assert PiAgent("openrouter").turn_ended({"type": parsed}) is True

    def it_keeps_the_turn_open_until_then() -> None:
        agent = PiAgent("openrouter")
        assert agent.turn_ended({"type": "turn_end"}) is False
        assert agent.turn_ended({"type": "response", "command": "prompt"}) is False
        assert agent.turn_ended({}) is False
