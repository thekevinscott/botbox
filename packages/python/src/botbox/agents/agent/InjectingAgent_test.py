from pathlib import Path
from typing import TYPE_CHECKING, get_type_hints

from botbox.agents.agent import Agent, InjectingAgent

if TYPE_CHECKING:
    from botbox.agents.HomeFiles import HomeFiles


def describe_injecting_agent() -> None:
    def it_is_an_agent() -> None:
        assert Agent in InjectingAgent.__mro__

    def it_names_a_credential_source_or_none() -> None:
        hints = get_type_hints(InjectingAgent.credential_source.fget)  # type: ignore[attr-defined]
        assert str(hints["return"]) == (
            "botbox.credential_proxy.CredentialSource.CredentialSource | None"
        )

    def it_recognises_an_agent_with_a_credential_source() -> None:
        assert isinstance(Injecting(), InjectingAgent)

    def it_recognises_one_that_has_its_credentials_copied() -> None:
        assert not isinstance(OneShot(), InjectingAgent)


class OneShot:
    image = "an-agent:latest"
    dockerfile = Path("/agents/an-agent.Dockerfile")
    home = "/home/agent"
    sessions_dir = "sessions"
    allow = ()

    def stage_auth(self, home: "HomeFiles") -> None: ...

    def command(self, prompt: str) -> str:
        return prompt


class Injecting(OneShot):
    credential_source = None
