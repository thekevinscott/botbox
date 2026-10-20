from pathlib import Path
from typing import Any, get_type_hints

from botbox.agents.agent import Agent, SessionAgent
from botbox.agents.claude import ClaudeAgent
from botbox.agents.pi import PiAgent


def describe_agent() -> None:
    def it_declares_what_an_agent_knows() -> None:
        assert set(get_type_hints(Agent)) == {
            "allow",
            "dockerfile",
            "home",
            "image",
            "transcripts",
        }

    def it_stages_credentials_into_a_home() -> None:
        assert get_type_hints(Agent.stage_auth) == {"home": Path, "return": type(None)}

    def it_renders_a_command_for_a_prompt() -> None:
        assert get_type_hints(Agent.command) == {"prompt": str, "return": str}

    def it_types_the_dockerfile_as_a_path() -> None:
        assert get_type_hints(Agent)["dockerfile"] is Path

    def it_types_the_egress_allowlist_as_a_tuple_of_hosts() -> None:
        assert get_type_hints(Agent)["allow"] == tuple[str, ...]


def describe_session_agent() -> None:
    def it_is_an_agent() -> None:
        assert Agent in SessionAgent.__mro__

    def it_renders_a_session_command() -> None:
        assert get_type_hints(SessionAgent.session_command) == {"return": str}

    def it_encodes_a_message_as_a_line() -> None:
        assert get_type_hints(SessionAgent.encode) == {"message": str, "return": str}

    def it_says_whether_an_event_ends_the_turn() -> None:
        assert get_type_hints(SessionAgent.turn_ended) == {
            "event": dict[str, Any],
            "return": bool,
        }

    def it_recognises_an_agent_with_a_session_mode() -> None:
        assert isinstance(PiAgent("openrouter"), SessionAgent)

    def it_recognises_an_agent_without_one() -> None:
        assert not isinstance(ClaudeAgent(), SessionAgent)
