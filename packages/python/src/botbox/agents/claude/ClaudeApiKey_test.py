from collections.abc import Iterator
from unittest.mock import patch

import pytest

from botbox.agents.claude.ClaudeApiKey import INJECTION, ClaudeApiKey

MODULE = f"{__package__}.ClaudeApiKey"


@pytest.fixture(autouse=True)
def collaborators() -> Iterator[None]:
    with (
        patch(f"{MODULE}.Credential", lambda injection, secret: (injection, secret)),
        patch(f"{MODULE}.INJECTION", "injection"),
    ):
        yield


def describe_ClaudeApiKey() -> None:
    def it_sends_the_key_as_it_is() -> None:
        read: object = ClaudeApiKey("sk-ant-api03-real").read()
        assert read == ("injection", "sk-ant-api03-real")

    def it_keeps_the_key_out_of_its_repr() -> None:
        assert "real" not in repr(ClaudeApiKey("sk-ant-api03-real"))

    def it_gives_the_box_a_placeholder_key() -> None:
        assert ClaudeApiKey("sk-ant-api03-real").placeholder == "sk-ant-api03-botbox-placeholder"

    def it_points_claude_code_at_the_proxy() -> None:
        assert ClaudeApiKey.env == {"ANTHROPIC_BASE_URL": "http://127.0.0.1:41894"}


def describe_the_injection() -> None:
    def it_goes_to_the_anthropic_api() -> None:
        assert INJECTION.upstream == "api.anthropic.com"

    def it_allows_only_the_messages_paths() -> None:
        assert INJECTION.paths == "/v1/messages(/count_tokens)?"

    def it_sets_the_key_as_x_api_key() -> None:
        assert INJECTION.header == "x-api-key"

    def it_strips_the_bearer_the_placeholder_also_goes_out_as() -> None:
        assert INJECTION.strip == ("Authorization",)
