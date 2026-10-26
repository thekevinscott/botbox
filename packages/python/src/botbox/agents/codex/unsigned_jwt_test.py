import base64
import json
from typing import Any

from botbox.agents.codex.unsigned_jwt import unsigned_jwt


def decoded(part: str) -> Any:
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def describe_unsigned_jwt() -> None:
    def it_carries_the_claims() -> None:
        assert decoded(unsigned_jwt({"exp": 1}).split(".")[1]) == {"exp": 1}

    def it_is_unsigned() -> None:
        header, _, signature = unsigned_jwt({}).split(".")
        assert decoded(header) == {"alg": "none", "typ": "JWT"}
        assert signature == "botbox-placeholder"
