import base64
import json
from typing import Any

import pytest

from botbox.agents.codex.jwt_claims import jwt_claims


def jwt(claims: Any) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"eyJhbGciOiJSUzI1NiJ9.{payload}.real-signature"


def describe_jwt_claims() -> None:
    def it_reads_an_unpadded_payload() -> None:
        assert jwt_claims(jwt({"a": "bc"})) == {"a": "bc"}

    @pytest.mark.parametrize("token", ["", "a.b", "a.b.c.d", "a.!!.c", jwt([])])
    def it_raises_value_error_for_anything_else(token: str) -> None:
        with pytest.raises(ValueError):
            jwt_claims(token)
