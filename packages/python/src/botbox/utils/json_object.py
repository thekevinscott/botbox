import json
from contextlib import suppress
from typing import Any


def json_object(line: bytes) -> dict[str, Any] | None:
    """`line` as a JSON object; None if it is not one."""
    with suppress(ValueError):
        event = json.loads(line)
        if isinstance(event, dict):
            return event
    return None
