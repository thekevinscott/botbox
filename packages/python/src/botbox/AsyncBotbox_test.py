import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import Mock, call, patch

import pytest

from botbox.AsyncBotbox import AsyncBotbox

AGENT_STEP = Mock(
    context=Path("/agents"),
    tag="an-agent:latest",
    file=Path("/agents/D"),
    contexts={"botbox": "/r"},
)
LAYER_STEP = Mock(
    context=Path("/consumer"), tag="an-agent-123:latest", file=Path("/consumer/D"), contexts={}
)


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
def docker_build(steps: list[str]) -> Iterator[Mock]:
    async def build(_context: Path, *, tag: str, **_options: Any) -> None:
        steps.append(f"build {tag}")

    with patch("botbox.AsyncBotbox.docker_build", autospec=True, side_effect=build) as m:
        yield m


class CommandFailed(Exception):
    def __init__(self, docker_command: list[str], return_code: int, stderr: str) -> None:
        self.docker_command = docker_command
        self.return_code = return_code
        self.stderr = stderr


class DockerException(Exception):
    def __init__(
        self, command_launched: list[str], return_code: int, stderr: bytes | None = None
    ) -> None:
        self.command_launched = command_launched
        self.return_code = return_code
        self.stderr = stderr


@pytest.fixture(autouse=True)
def exceptions() -> Iterator[None]:
    with (
        patch("botbox.AsyncBotbox.CommandFailed", CommandFailed),
        patch("botbox.AsyncBotbox.DockerException", DockerException),
    ):
        yield


@pytest.fixture(autouse=True)
def lock(steps: list[str]) -> Iterator[None]:
    @asynccontextmanager
    async def lock(tag: str) -> AsyncIterator[None]:
        steps.append(f"lock {tag}")
        try:
            yield
        finally:
            steps.append(f"unlock {tag}")

    with patch("botbox.AsyncBotbox.async_build_lock", lock):
        yield


def describe_async_botbox() -> None:
    def it_keeps_the_agent(agent: Mock) -> None:
        assert AsyncBotbox(agent).agent is agent

    def it_takes_its_options_by_keyword_only(agent: Mock, layer: Path) -> None:
        with pytest.raises(TypeError):
            AsyncBotbox(agent, layer)  # type: ignore[call-arg]

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

    async def it_returns_the_only_steps_tag(agent: Mock, build_steps: Mock) -> None:
        build_steps.return_value = [AGENT_STEP]
        assert await AsyncBotbox(agent).build() == "an-agent:latest"

    async def it_builds_each_step_with_the_docker_sdk(agent: Mock, docker_build: Mock) -> None:
        await AsyncBotbox(agent).build()
        assert docker_build.call_args_list == [
            call(
                Path("/agents"),
                tag="an-agent:latest",
                file=Path("/agents/D"),
                contexts={"botbox": "/r"},
            ),
            call(
                Path("/consumer"),
                tag="an-agent-123:latest",
                file=Path("/consumer/D"),
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
        agent: Mock, docker_build: Mock, steps: list[str]
    ) -> None:
        docker_build.side_effect = RuntimeError("agent failed")
        with pytest.raises(RuntimeError, match="agent failed"):
            await AsyncBotbox(agent).build()
        assert steps == ["lock an-agent:latest", "unlock an-agent:latest"]

    async def it_raises_a_failed_build_as_botboxs_docker_exception(
        agent: Mock, docker_build: Mock
    ) -> None:
        failed = CommandFailed(["docker", "buildx", "build"], 1, "ERROR: failed to solve\n")
        docker_build.side_effect = failed
        with pytest.raises(DockerException) as raised:
            await AsyncBotbox(agent).build()
        assert raised.value.command_launched == ["docker", "buildx", "build"]
        assert raised.value.return_code == 1
        assert raised.value.stderr == b"ERROR: failed to solve\n"
        assert raised.value.__cause__ is failed

    async def it_releases_the_lock_when_a_build_fails(
        agent: Mock, docker_build: Mock, steps: list[str]
    ) -> None:
        docker_build.side_effect = CommandFailed(["docker"], 1, "")
        with pytest.raises(DockerException):
            await AsyncBotbox(agent).build()
        assert steps == ["lock an-agent:latest", "unlock an-agent:latest"]

    async def it_releases_the_lock_when_a_build_is_cancelled(
        agent: Mock, docker_build: Mock, steps: list[str]
    ) -> None:
        started = asyncio.Event()

        async def hang(*_args: object, **_options: object) -> None:
            started.set()
            await asyncio.Event().wait()

        docker_build.side_effect = hang
        build = asyncio.create_task(AsyncBotbox(agent).build())
        await started.wait()
        build.cancel()
        with pytest.raises(asyncio.CancelledError):
            await build
        assert steps == ["lock an-agent:latest", "unlock an-agent:latest"]
