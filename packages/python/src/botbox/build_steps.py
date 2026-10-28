import hashlib
from pathlib import Path
from typing import NamedTuple

from botbox.agents.Agent import Agent
from botbox.lockdown import RELAY_DIR


class BuildStep(NamedTuple):
    context: Path
    tag: str
    file: Path
    contexts: dict[str, str | Path]


def build_steps(agent: Agent, dockerfile: Path | None) -> list[BuildStep]:
    """The agent's image, then `dockerfile` on top if given, in build order.

    The layer is tagged after the agent's image and a hash of the Dockerfile's path.
    """
    steps = [
        BuildStep(agent.dockerfile.parent, agent.image, agent.dockerfile, {"botbox": RELAY_DIR})
    ]
    if dockerfile is not None:
        digest = hashlib.sha256(str(dockerfile).encode()).hexdigest()[:12]
        tag = f"{agent.image.split(':')[0]}-{digest}:latest"
        steps.append(BuildStep(dockerfile.parent, tag, dockerfile, {}))
    return steps
