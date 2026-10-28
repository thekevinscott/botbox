from typing import Protocol, runtime_checkable

from botbox.agents.agent.Agent import Agent
from botbox.credential_proxy import CredentialSource


@runtime_checkable
class InjectingAgent(Agent, Protocol):
    """An agent whose credential the proxy sends upstream, so the box never holds it.

    An agent without `credential_source` has its credentials copied in by `stage_auth`.
    """

    @property
    def credential_source(self) -> CredentialSource | None:
        """The host credential the proxy injects, or None to have `stage_auth` copy it."""
        ...
