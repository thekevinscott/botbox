import re
from pathlib import Path
from unittest.mock import Mock

import pytest

from botbox.build_steps import BuildStep, build_steps

RELAY_DIR = Path(__file__).with_name("relay")
AGENT_DOCKERFILE = Path("/agents/an-agent.Dockerfile")


@pytest.fixture
def agent() -> Mock:
    return Mock(image="an-agent:latest", dockerfile=AGENT_DOCKERFILE)


def describe_build_steps() -> None:
    def it_builds_only_the_agent_image_without_a_dockerfile(agent: Mock) -> None:
        assert build_steps(agent, None) == [
            BuildStep(Path("/agents"), "an-agent:latest", AGENT_DOCKERFILE, {"botbox": RELAY_DIR})
        ]

    def it_builds_the_layer_in_its_directory_after_the_agent_image(agent: Mock) -> None:
        layer = Path("/consumer/Dockerfile")
        agent_step, layer_step = build_steps(agent, layer)
        assert agent_step.tag == "an-agent:latest"
        assert layer_step == BuildStep(Path("/consumer"), layer_step.tag, layer, {})

    def it_tags_the_layer_after_the_agent_image_and_the_dockerfile(agent: Mock) -> None:
        _, step = build_steps(agent, Path("/consumer/Dockerfile"))
        assert re.fullmatch(r"an-agent-[0-9a-f]{12}:latest", step.tag)

    def it_tags_different_dockerfiles_differently(agent: Mock) -> None:
        _, one = build_steps(agent, Path("/one/Dockerfile"))
        _, other = build_steps(agent, Path("/other/Dockerfile"))
        assert one.tag != other.tag
