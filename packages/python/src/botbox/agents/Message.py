from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Message:
    """One message an agent's CLI printed: its harness's name for its `type`, its text, and the
    event it came in, unchanged."""

    type: str
    text: str
    event: dict[str, Any]
