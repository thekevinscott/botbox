import json
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from botbox.agents.codex.CodexApiKey import CodexApiKey

MODULE = f"{__package__}.CodexApiKey"


@pytest.fixture(autouse=True)
def collaborators() -> Iterator[None]:
    with (
        patch(f"{MODULE}.Credential", lambda injection, secret: (injection, secret)),
        patch(f"{MODULE}.INJECTION", "injection"),
    ):
        yield


def describe_CodexApiKey() -> None:
    def it_points_codex_at_the_proxys_api() -> None:
        assert CodexApiKey.base_url == "http://127.0.0.1:41894/v1"

    def it_needs_no_environment() -> None:
        assert CodexApiKey.env == {}

    def it_sends_the_key_as_a_bearer() -> None:
        read: object = CodexApiKey("sk-real").read()
        assert read == ("injection", "Bearer sk-real")

    def it_gives_the_box_a_placeholder_key() -> None:
        placeholder = CodexApiKey("sk-real").placeholder()
        assert "sk-real" not in placeholder
        assert json.loads(placeholder) == {
            "auth_mode": "apikey",
            "OPENAI_API_KEY": "sk-botbox-placeholder",
        }

    def it_keeps_the_key_out_of_its_repr() -> None:
        assert "sk-real" not in repr(CodexApiKey("sk-real"))
