import dataclasses

import pytest

from botbox.agents.Message import Message


def describe_message() -> None:
    def it_holds_the_type_text_and_event() -> None:
        event = {"type": "assistant"}
        message = Message("assistant", "hi", event)
        assert (message.type, message.text, message.event) == ("assistant", "hi", event)

    def it_is_frozen() -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            Message("assistant", "hi", {}).text = "bye"  # type: ignore[misc]
