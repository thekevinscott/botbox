import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from botbox.agents.pi.OpenRouterKey import OpenRouterKey

MODULE = f"{__package__}.OpenRouterKey"


@pytest.fixture(autouse=True)
def collaborators() -> Iterator[None]:
    with (
        patch(f"{MODULE}.Credential", lambda injection, secret: (injection, secret)),
        patch(f"{MODULE}.INJECTION", "injection"),
        patch(f"{MODULE}.BASE_URL", "http://proxy/api/v1"),
    ):
        yield


@pytest.fixture
def auth(tmp_path: Path) -> Path:
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "openrouter": {"type": "api_key", "key": "sk-or-v1-host"},
                "anthropic": {"type": "api_key", "key": "sk-ant-other"},
            }
        )
    )
    return path


@pytest.fixture
def models(tmp_path: Path) -> Path:
    return tmp_path / "models.json"


def write(path: Path, providers: dict[str, Any]) -> Path:
    path.write_text(json.dumps({"providers": providers}))
    return path


def provider(text: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(text)
    assert list(loaded["providers"]) == ["openrouter"]
    return dict(loaded["providers"]["openrouter"])


def describe_OpenRouterKey() -> None:
    def it_keeps_its_path(auth: Path) -> None:
        assert OpenRouterKey(auth).auth == auth

    def it_points_pi_at_the_proxy_through_models_json_alone() -> None:
        assert OpenRouterKey.env == {}

    def describe_read() -> None:
        def it_sends_the_hosts_key_as_a_bearer(auth: Path) -> None:
            read: object = OpenRouterKey(auth).read()
            assert read == ("injection", "Bearer sk-or-v1-host")

        def it_sends_the_given_key_instead(tmp_path: Path) -> None:
            read: object = OpenRouterKey(tmp_path / "missing", "sk-or-v1-given").read()
            assert read == ("injection", "Bearer sk-or-v1-given")

        def it_reads_the_host_file_on_every_call(auth: Path) -> None:
            key = OpenRouterKey(auth)
            key.read()
            auth.write_text(json.dumps({"openrouter": {"type": "api_key", "key": "sk-or-v1-new"}}))
            read: object = key.read()
            assert read == ("injection", "Bearer sk-or-v1-new")

        def it_raises_for_a_missing_file(tmp_path: Path) -> None:
            with pytest.raises(FileNotFoundError):
                OpenRouterKey(tmp_path / "missing").read()

        @pytest.mark.parametrize(
            "text",
            [
                "[]",
                "{}",
                '{"openrouter": []}',
                '{"openrouter": {"type": "api_key"}}',
                '{"openrouter": {"type": "api_key", "key": ""}}',
                '{"openrouter": {"type": "api_key", "key": 1}}',
            ],
        )
        def it_names_the_file_with_no_key(auth: Path, text: str) -> None:
            auth.write_text(text)
            with pytest.raises(ValueError, match=rf"^{auth} holds no OpenRouter key$"):
                OpenRouterKey(auth).read()

        @pytest.mark.parametrize("key", ["!op read op://vault/or", "OPENROUTER_API_KEY", "_k1"])
        def it_refuses_a_command_or_an_env_var_name(auth: Path, key: str) -> None:
            auth.write_text(json.dumps({"openrouter": {"type": "api_key", "key": key}}))
            with pytest.raises(ValueError, match=r"command or an env var name.*literal key"):
                OpenRouterKey(auth).read()

    def describe_placeholder() -> None:
        def it_holds_a_placeholder_key_for_openrouter_alone(auth: Path) -> None:
            assert json.loads(OpenRouterKey(auth).placeholder()) == {
                "openrouter": {"type": "api_key", "key": "sk-or-v1-botbox-placeholder"}
            }

    def describe_models() -> None:
        def it_points_openrouter_at_the_proxy_without_a_host_file(auth: Path) -> None:
            assert json.loads(OpenRouterKey(auth).models(None)) == {
                "providers": {"openrouter": {"baseUrl": "http://proxy/api/v1"}}
            }

        def it_points_openrouter_at_the_proxy_when_the_host_has_no_entry(
            auth: Path, models: Path
        ) -> None:
            write(models, {"ollama": {"baseUrl": "http://models.example", "apiKey": "o"}})
            assert provider(OpenRouterKey(auth).models(models)) == {
                "baseUrl": "http://proxy/api/v1"
            }

        def it_keeps_the_hosts_entry_without_its_key_headers_or_base_url(
            auth: Path, models: Path
        ) -> None:
            write(
                models,
                {
                    "openrouter": {
                        "baseUrl": "https://openrouter.ai/api/v1",
                        "apiKey": "sk-or-v1-models",
                        "headers": {"X-Secret": "s"},
                        "api": "openai-completions",
                        "compat": {"supportsDeveloperRole": False},
                    }
                },
            )
            assert provider(OpenRouterKey(auth).models(models)) == {
                "baseUrl": "http://proxy/api/v1",
                "api": "openai-completions",
                "compat": {"supportsDeveloperRole": False},
            }

        def it_drops_each_models_headers_and_base_url(auth: Path, models: Path) -> None:
            write(
                models,
                {
                    "openrouter": {
                        "models": [
                            {"id": "a", "baseUrl": "https://elsewhere", "headers": {"k": "v"}},
                            "odd",
                        ],
                        "modelOverrides": {"b": {"name": "B", "headers": {"k": "v"}}},
                    }
                },
            )
            assert provider(OpenRouterKey(auth).models(models)) == {
                "baseUrl": "http://proxy/api/v1",
                "models": [{"id": "a"}, "odd"],
                "modelOverrides": {"b": {"name": "B"}},
            }

        def it_leaves_a_malformed_model_list_as_it_is(auth: Path, models: Path) -> None:
            write(models, {"openrouter": {"models": "odd"}})
            assert provider(OpenRouterKey(auth).models(models))["models"] == "odd"

        def it_reads_models_json_with_comments_and_trailing_commas(
            auth: Path, models: Path
        ) -> None:
            models.write_text('// c\n{"providers": {"openrouter": {"api": "x",},},}\n')
            assert provider(OpenRouterKey(auth).models(models)) == {
                "api": "x",
                "baseUrl": "http://proxy/api/v1",
            }
