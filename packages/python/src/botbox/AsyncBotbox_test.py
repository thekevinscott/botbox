from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import Mock, call, patch

import pytest

from botbox.AsyncBotbox import AsyncBotbox
from botbox.build_steps import BuildStep

AGENT_STEP = BuildStep(
    Path("/agents"), "an-agent:latest", Path("/agents/D"), {"botbox": Path("/r")}
)
LAYER_STEP = BuildStep(Path("/consumer"), "an-agent-123:latest", Path("/consumer/Dockerfile"), {})


@pytest.fixture
def agent() -> Mock:
    return Mock(image="an-agent:latest")


@pytest.fixture
def layer(tmp_path: Path) -> Path:
    return tmp_path / "consumer" / "Dockerfile"


@pytest.fixture
def steps() -> list[str]:
    """Each lock taken and released, and each build, in order."""
    return []


@pytest.fixture(autouse=True)
def build_steps() -> Iterator[Mock]:
    with patch("botbox.AsyncBotbox.build_steps", autospec=True) as m:
        m.return_value = [AGENT_STEP, LAYER_STEP]
        yield m


@pytest.fixture(autouse=True)
def buildx(steps: list[str]) -> Iterator[Mock]:
    async def build(_context: Path, *, tag: str, **_options: Any) -> None:
        steps.append(f"build {tag}")

    with patch("botbox.AsyncBotbox.buildx", autospec=True, side_effect=build) as m:
        yield m


@pytest.fixture(autouse=True)
def lock(steps: list[str]) -> Iterator[None]:
    @asynccontextmanager
    async def lock(tag: str) -> AsyncIterator[None]:
        steps.append(f"lock {tag}")
        yield
        steps.append(f"unlock {tag}")

    with patch("botbox.AsyncBotbox.async_build_lock", lock):
        yield


def describe_async_botbox() -> None:
    def it_keeps_the_agent(agent: Mock) -> None:
        assert AsyncBotbox(agent).agent is agent

    def it_takes_its_options_by_keyword_only(agent: Mock, layer: Path) -> None:
        with pytest.raises(TypeError):
            AsyncBotbox(agent, layer)  # type: ignore[misc]

    def it_has_no_dockerfile_by_default(agent: Mock) -> None:
        assert AsyncBotbox(agent).dockerfile is None

    def it_holds_the_dockerfile_as_an_absolute_path(agent: Mock, layer: Path) -> None:
        assert AsyncBotbox(agent, dockerfile=str(layer)).dockerfile == layer

    def it_holds_the_extra_hosts_as_a_tuple(agent: Mock) -> None:
        assert AsyncBotbox(agent, allow=["registry.npmjs.org"]).allow == ("registry.npmjs.org",)

    def it_refuses_a_bare_string_that_would_split_into_characters(agent: Mock) -> None:
        with pytest.raises(TypeError, match=r"allow=\('github\.com',\)"):
            AsyncBotbox(agent, allow="github.com")


def describe_build() -> None:
    async def it_plans_the_build_from_the_agent_and_dockerfile(
        agent: Mock, layer: Path, build_steps: Mock
    ) -> None:
        await AsyncBotbox(agent, dockerfile=layer).build()
        build_steps.assert_called_once_with(agent, layer)

    async def it_returns_the_last_steps_tag(agent: Mock) -> None:
        assert await AsyncBotbox(agent).build() == "an-agent-123:latest"

    async def it_builds_each_step_with_buildx(agent: Mock, buildx: Mock) -> None:
        await AsyncBotbox(agent).build()
        assert buildx.call_args_list == [
            call(
                Path("/agents"),
                tag="an-agent:latest",
                file=Path("/agents/D"),
                contexts={"botbox": Path("/r")},
            ),
            call(
                Path("/consumer"),
                tag="an-agent-123:latest",
                file=Path("/consumer/Dockerfile"),
                contexts={},
            ),
        ]

    async def it_holds_each_tags_lock_only_while_building_it(agent: Mock, steps: list[str]) -> None:
        await AsyncBotbox(agent).build()
        assert steps == [
            "lock an-agent:latest",
            "build an-agent:latest",
            "unlock an-agent:latest",
            "lock an-agent-123:latest",
            "build an-agent-123:latest",
            "unlock an-agent-123:latest",
        ]

    async def it_stops_at_the_first_failed_step(
        agent: Mock, buildx: Mock, steps: list[str]
    ) -> None:
        buildx.side_effect = RuntimeError("agent failed")
        with pytest.raises(RuntimeError, match="agent failed"):
            await AsyncBotbox(agent).build()
        assert steps == ["lock an-agent:latest", "unlock an-agent:latest"]
