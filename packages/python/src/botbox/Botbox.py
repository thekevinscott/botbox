import hashlib
from collections.abc import Sequence
from pathlib import Path

from python_on_whales import docker

from botbox.agents.agent import Agent


class Botbox:
    """An agent, an optional image layer on top of it, and the extra hosts its proxy admits."""

    def __init__(
        self,
        agent: Agent,
        *,
        dockerfile: str | Path | None = None,
        allow: Sequence[str] = (),
    ) -> None:
        self.agent = agent
        self.dockerfile = None if dockerfile is None else Path(dockerfile).resolve()
        self.allow = tuple(allow)

    def build(self) -> str:
        """Build the agent's image, then `dockerfile` on top, and return the final tag.

        Built on every call; Docker's layer cache keeps an unchanged build fast.
        """
        agent_dockerfile = self.agent.dockerfile
        docker.build(
            agent_dockerfile.parent, tags=self.agent.image, file=agent_dockerfile, progress=False
        )
        if self.dockerfile is None:
            return self.agent.image
        digest = hashlib.sha256(str(self.dockerfile).encode()).hexdigest()[:12]
        tag = f"{self.agent.image.split(':')[0]}-{digest}:latest"
        docker.build(self.dockerfile.parent, tags=tag, file=self.dockerfile, progress=False)
        return tag
