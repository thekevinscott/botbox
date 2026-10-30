from collections.abc import Iterator
from unittest.mock import Mock, patch

import pytest

from botbox.agents.message_from import message_from

EVENT = {"type": "message_end"}


@pytest.fixture(autouse=True)
def message() -> Iterator[Mock]:
    with patch("botbox.agents.message_from.Message", autospec=True) as m:
        yield m


def describe_message_from() -> None:
    def it_takes_string_content_as_the_text(message: Mock) -> None:
        made = message_from("user", {"content": "hi"}, EVENT)
        assert made is message.return_value
        message.assert_called_once_with("user", "hi", EVENT)

    def it_joins_the_text_parts_and_skips_the_rest(message: Mock) -> None:
        content = [
            {"type": "text", "text": "one "},
            {"type": "toolCall", "text": "not text"},
            {"type": "summary", "text": "not text"},
            {"type": "text", "text": 2},
            "loose",
            {"type": "text", "text": "two"},
        ]
        message_from("assistant", {"content": content}, EVENT)
        message.assert_called_once_with("assistant", "one two", EVENT)

    @pytest.mark.parametrize("content", [None, 3, {"text": "hi"}])
    def it_has_no_text_without_string_or_list_content(message: Mock, content: object) -> None:
        message_from("assistant", {"content": content}, EVENT)
        message.assert_called_once_with("assistant", "", EVENT)

    @pytest.mark.parametrize(
        ("kind", "body"), [(None, {}), (3, {}), ("user", "hi"), ("user", None)]
    )
    def it_makes_none_without_a_string_kind_and_an_object(
        message: Mock, kind: object, body: object
    ) -> None:
        assert message_from(kind, body, EVENT) is None
        message.assert_not_called()
