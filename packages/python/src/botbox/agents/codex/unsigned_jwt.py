import base64
import json
from collections.abc import Mapping
from typing import Any


def unsigned_jwt(claims: Mapping[str, Any]) -> str:
    """A JWT with `claims` and no signature, which Codex parses but nothing upstream accepts."""
    parts = ({"alg": "none", "typ": "JWT"}, claims)
    encoded = (base64.urlsafe_b64encode(json.dumps(p).encode()).rstrip(b"=") for p in parts)
    return ".".join(e.decode() for e in encoded) + ".botbox-placeholder"
