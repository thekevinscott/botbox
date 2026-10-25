from pathlib import Path
from typing import Any, get_type_hints

from botbox.agents.agent import Agent, SessionAgent


def describe_agent() -> None:
    def it_declares_what_an_agent_knows() -> None:
        assert set(get_type_hints(Agent)) == {
            "allow",
            "dockerfile",
            "home",
            "image",
            "sessions_dir",
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
        assert isinstance(Streaming(), SessionAgent)

    def it_recognises_an_agent_without_one() -> None:
        assert not isinstance(OneShot(), SessionAgent)


class OneShot:
    image = "an-agent:latest"
    dockerfile = Path("/agents/an-agent.Dockerfile")
    home = "/home/agent"
    sessions_dir = "sessions"
    allow = ()

    def stage_auth(self, home: Path) -> None: ...

    def command(self, prompt: str) -> str:
        return prompt


class Streaming(OneShot):
    def session_command(self) -> str:
        return "an-agent --stream"

    def encode(self, message: str) -> str:
        return message

    def turn_ended(self, event: dict[str, Any]) -> bool:
        return bool(event)
