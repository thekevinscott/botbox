from typing import Any

from botbox.agents.Message import Message


def message_from(kind: object, message: object, event: dict[str, Any]) -> Message | None:
    """A Message of `kind` from `message`, an object whose `content` is a string or a list of
    parts; its text is the string, or the text parts joined. None if `kind` is not a string or
    `message` not an object."""
    if not isinstance(kind, str) or not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return Message(kind, content, event)
    parts = content if isinstance(content, list) else []
    text = "".join(
        part["text"]
        for part in parts
        if isinstance(part, dict)
        and part.get("type") == "text"
        and isinstance(part.get("text"), str)
    )
    return Message(kind, text, event)
