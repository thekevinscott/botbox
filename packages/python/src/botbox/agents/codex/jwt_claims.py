import base64
import json
from typing import Any


def jwt_claims(token: str) -> dict[str, Any]:
    """The claims of a JWT, unverified. Raises ValueError for anything else."""
    match token.split("."):
        case [_, payload, _]:
            pass
        case _:
            raise ValueError("not a JWT")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    if not isinstance(claims, dict):
        raise ValueError("not a JWT")
    return claims
