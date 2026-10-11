import re
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from botbox.Botbox import Botbox

AGENT_DOCKERFILE = Path("/agents/an-agent.Dockerfile")


@pytest.fixture
def agent() -> Mock:
    return Mock(image="an-agent:latest", dockerfile=AGENT_DOCKERFILE)


@pytest.fixture(autouse=True)
def docker() -> Iterator[MagicMock]:
    with patch("botbox.Botbox.docker", autospec=True) as m:
        yield m


@pytest.fixture
def layer(tmp_path: Path) -> Path:
    return tmp_path / "consumer" / "Dockerfile"


def describe_botbox() -> None:
    def it_keeps_the_agent(agent: Mock) -> None:
        assert Botbox(agent).agent is agent

    def it_takes_its_options_by_keyword_only(agent: Mock, layer: Path) -> None:
        with pytest.raises(TypeError):
            Botbox(agent, layer)  # type: ignore[call-arg]

    def it_has_no_dockerfile_by_default(agent: Mock) -> None:
        assert Botbox(agent).dockerfile is None

    def it_holds_the_dockerfile_as_an_absolute_path(agent: Mock, layer: Path) -> None:
        assert Botbox(agent, dockerfile=str(layer)).dockerfile == layer

    def it_allows_nothing_extra_by_default(agent: Mock) -> None:
        assert Botbox(agent).allow == ()

    def it_holds_the_extra_hosts_as_a_tuple(agent: Mock) -> None:
        assert Botbox(agent, allow=["registry.npmjs.org"]).allow == ("registry.npmjs.org",)


def describe_build() -> None:
    def describe_without_a_dockerfile() -> None:
        def it_returns_the_agents_tag(agent: Mock) -> None:
            assert Botbox(agent).build() == "an-agent:latest"

        def it_builds_the_agent_dockerfile_quietly_in_its_directory(
            agent: Mock, docker: MagicMock
        ) -> None:
            Botbox(agent).build()
            assert docker.build.call_args_list == [
                call(Path("/agents"), tags="an-agent:latest", file=AGENT_DOCKERFILE, progress=False)
            ]

    def describe_with_a_dockerfile() -> None:
        def it_tags_the_layer_after_the_agent_image_and_the_dockerfile(
            agent: Mock, layer: Path
        ) -> None:
            assert re.fullmatch(
                r"an-agent-[0-9a-f]{12}:latest", Botbox(agent, dockerfile=layer).build()
            )

        def it_builds_the_layer_quietly_in_its_directory_after_the_agent_image(
            agent: Mock, docker: MagicMock, layer: Path
        ) -> None:
            tag = Botbox(agent, dockerfile=layer).build()
            assert docker.build.call_args_list == [
                call(
                    Path("/agents"), tags="an-agent:latest", file=AGENT_DOCKERFILE, progress=False
                ),
                call(layer.parent, tags=tag, file=layer, progress=False),
            ]
