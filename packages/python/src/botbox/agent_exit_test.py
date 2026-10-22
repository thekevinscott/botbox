from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from botbox.agent_exit import agent_exit

COMMAND = ["docker", "run", "--name", "botbox-agent-1", "image"]


class DockerException(Exception):
    def __init__(self, docker_command: list[str], return_code: int, stderr: str) -> None:
        self.docker_command = docker_command
        self.return_code = return_code
        self.stderr = stderr


@pytest.fixture(autouse=True)
def docker_exception() -> Iterator[None]:
    with patch("botbox.agent_exit.DockerException", DockerException):
        yield


@pytest.fixture
def state() -> dict[str, Any]:
    # Built, not a literal: the status comes from parsed JSON, never an interned string.
    return {"Status": "".join(["exit", "ed"]), "ExitCode": 125}


@pytest.fixture(autouse=True)
def inspect(state: dict[str, Any]) -> Iterator[AsyncMock]:
    with patch("botbox.agent_exit.inspect_container", autospec=True) as m:
        m.return_value = {"Name": "/botbox-agent-1", "State": state}
        yield m


@pytest.fixture(autouse=True)
def version() -> Iterator[AsyncMock]:
    with patch("botbox.agent_exit.version", autospec=True) as m:
        yield m


def describe_agent_exit() -> None:
    async def it_reads_the_exit_code_from_the_stopped_container(inspect: AsyncMock) -> None:
        assert await agent_exit("botbox-agent-1", COMMAND, 125, "") == 125
        inspect.assert_awaited_once_with("botbox-agent-1")

    async def it_believes_the_container_over_the_client(state: dict[str, Any]) -> None:
        state["ExitCode"] = 7
        assert await agent_exit("botbox-agent-1", COMMAND, 125, "") == 7

    async def it_warns_when_the_container_was_killed_for_memory(state: dict[str, Any]) -> None:
        state.update(ExitCode=137, OOMKilled=True)
        with pytest.warns(RuntimeWarning, match="botbox-agent-1 ran out of memory"):
            assert await agent_exit("botbox-agent-1", COMMAND, 137, "") == 137

    @pytest.mark.parametrize("client", [-9, -15, -1])
    async def it_raises_with_a_killed_client_even_though_the_container_exited(
        client: int,
    ) -> None:
        with pytest.raises(DockerException) as raised:
            await agent_exit("botbox-agent-1", COMMAND, client, "trunc")
        assert raised.value.docker_command == COMMAND
        assert raised.value.return_code == client
        assert raised.value.stderr == "trunc"

    async def it_takes_a_client_exit_of_zero(state: dict[str, Any]) -> None:
        state["ExitCode"] = 0
        assert await agent_exit("botbox-agent-1", COMMAND, 0, "") == 0

    @pytest.mark.parametrize("status", ["running", "created", "dead"])
    async def it_raises_with_the_client_when_the_container_never_exited(
        state: dict[str, Any], status: str
    ) -> None:
        state["Status"] = status
        with pytest.raises(DockerException) as raised:
            await agent_exit("botbox-agent-1", COMMAND, -9, "lost the attach\n")
        assert raised.value.docker_command == COMMAND
        assert raised.value.return_code == -9
        assert raised.value.stderr == "lost the attach\n"

    async def it_returns_minus_one_when_the_daemon_went_away(
        inspect: AsyncMock, version: AsyncMock
    ) -> None:
        inspect.side_effect = DockerException(["docker", "container", "inspect"], 1, "")
        version.side_effect = DockerException(["docker", "version"], 1, "Cannot connect")
        assert await agent_exit("botbox-agent-1", COMMAND, 125, "") == -1

    async def it_returns_minus_one_when_the_daemon_went_away_with_a_killed_client(
        inspect: AsyncMock, version: AsyncMock
    ) -> None:
        inspect.side_effect = DockerException(["docker", "container", "inspect"], 1, "")
        version.side_effect = DockerException(["docker", "version"], 1, "Cannot connect")
        assert await agent_exit("botbox-agent-1", COMMAND, -9, "") == -1

    async def it_raises_with_the_client_when_there_is_no_such_container(
        inspect: AsyncMock, version: AsyncMock
    ) -> None:
        inspect.side_effect = DockerException(["docker", "container", "inspect"], 1, "No such")
        with pytest.raises(DockerException) as raised:
            await agent_exit("botbox-agent-1", COMMAND, 125, "Unable to find image\n")
        assert raised.value.docker_command == COMMAND
        assert raised.value.return_code == 125
        assert raised.value.stderr == "Unable to find image\n"
        version.assert_awaited_once_with()
