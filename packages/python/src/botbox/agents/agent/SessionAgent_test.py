from pathlib import Path
from typing import TYPE_CHECKING, Any, get_type_hints

from botbox.agents.agent import Agent, SessionAgent

if TYPE_CHECKING:
    from botbox.agents.HomeFiles import HomeFiles


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
        assert isinstance(Streaming(), SessionAgent)

    def it_recognises_an_agent_without_one() -> None:
        assert not isinstance(OneShot(), SessionAgent)


class OneShot:
    image = "an-agent:latest"
    dockerfile = Path("/agents/an-agent.Dockerfile")
    home = "/home/agent"
    sessions_dir = "sessions"
    allow = ()

    def stage_auth(self, home: "HomeFiles") -> None: ...

    def command(self, prompt: str) -> str:
        return prompt


class Streaming(OneShot):
    def session_command(self) -> str:
        return "an-agent --stream"

    def encode(self, message: str) -> str:
        return message

    def turn_ended(self, event: dict[str, Any]) -> bool:
        return bool(event)
