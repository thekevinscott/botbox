from pathlib import Path
from typing import TYPE_CHECKING, get_type_hints

import pytest

from botbox.agents.Agent import Agent

if TYPE_CHECKING:
    from botbox.agents.HomeFiles import HomeFiles


def describe_agent() -> None:
    def it_declares_what_an_agent_knows() -> None:
        assert set(get_type_hints(Agent)) == {
            "allow",
            "credential_source",
            "dockerfile",
            "home",
            "image",
            "sessions_dir",
        }

    def it_types_the_dockerfile_as_a_path() -> None:
        assert get_type_hints(Agent)["dockerfile"] is Path

    def it_types_the_egress_allowlist_as_a_tuple_of_hosts() -> None:
        assert get_type_hints(Agent)["allow"] == tuple[str, ...]

    def it_has_its_credentials_copied_in_by_default() -> None:
        assert OneShot().credential_source is None

    def it_writes_each_stdout_line_unchanged_by_default() -> None:
        line = b'{"type":"x"}\n'
        assert OneShot().filter_stdout(line) is line

    def describe_abstract_methods() -> None:
        def it_refuses_a_subclass_without_stage_auth() -> None:
            with pytest.raises(TypeError, match="stage_auth"):
                NoStageAuth()  # type: ignore[abstract]

        def it_refuses_a_subclass_without_command() -> None:
            with pytest.raises(TypeError, match="command"):
                NoCommand()  # type: ignore[abstract]

    def describe_without_a_session_mode() -> None:
        def it_has_no_session_command() -> None:
            with pytest.raises(
                NotImplementedError, match=r"^NOT IMPLEMENTED: OneShot has no session mode\.$"
            ):
                OneShot().session_command()

        def it_encodes_nothing() -> None:
            with pytest.raises(
                NotImplementedError, match=r"^NOT IMPLEMENTED: OneShot has no session mode\.$"
            ):
                OneShot().encode("hi")

        def it_ends_no_turn() -> None:
            with pytest.raises(
                NotImplementedError, match=r"^NOT IMPLEMENTED: OneShot has no session mode\.$"
            ):
                OneShot().turn_ended({"type": "turn/completed"})


class OneShot(Agent):
    image = "an-agent:latest"
    dockerfile = Path("/agents/an-agent.Dockerfile")
    home = "/home/agent"
    sessions_dir = "sessions"
    allow = ()

    def stage_auth(self, home: "HomeFiles") -> None: ...

    def command(self, prompt: str) -> str:
        return prompt


class NoStageAuth(Agent):
    def command(self, prompt: str) -> str:
        return prompt


class NoCommand(Agent):
    def stage_auth(self, home: "HomeFiles") -> None: ...
