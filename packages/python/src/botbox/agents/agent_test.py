from pathlib import Path
from typing import get_type_hints

from botbox.agents.agent import Agent


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

    def it_types_the_dockerfile_as_a_path() -> None:
        assert get_type_hints(Agent)["dockerfile"] is Path

    def it_types_the_egress_allowlist_as_a_tuple_of_hosts() -> None:
        assert get_type_hints(Agent)["allow"] == tuple[str, ...]
