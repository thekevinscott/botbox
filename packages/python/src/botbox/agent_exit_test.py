from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

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


@pytest.fixture(autouse=True)
def run_result() -> Iterator[Mock]:
    with patch("botbox.agent_exit.RunResult") as m:
        yield m


@pytest.fixture
def state() -> dict[str, Any]:
    # Built, not a literal: the status comes from parsed JSON, never an interned string.
    return {"Status": "".join(["exit", "ed"]), "ExitCode": 125}


@pytest.fixture
def inspect(state: dict[str, Any]) -> AsyncMock:
    return AsyncMock(return_value={"Name": "/botbox-agent-1", "State": state})


@pytest.fixture
def container(inspect: AsyncMock) -> Mock:
    return Mock(docker_command=COMMAND, inspect=inspect)


def describe_agent_exit() -> None:
    async def it_reads_the_exit_code_from_the_stopped_container(
        inspect: AsyncMock, container: Mock, run_result: Mock
    ) -> None:
        assert await agent_exit(container, 125, "") is run_result.return_value
        run_result.assert_called_once_with(125, oom_killed=False)
        inspect.assert_awaited_once_with()

    async def it_believes_the_container_over_the_client(
        state: dict[str, Any], container: Mock, run_result: Mock
    ) -> None:
        state["ExitCode"] = 7
        assert await agent_exit(container, 125, "") is run_result.return_value
        run_result.assert_called_once_with(7, oom_killed=False)

    @pytest.mark.parametrize("client", [-9, -15, -1])
    async def it_raises_with_a_killed_client_even_though_the_container_exited(
        client: int, container: Mock
    ) -> None:
        with pytest.raises(DockerException) as raised:
            await agent_exit(container, client, "trunc")
        assert raised.value.docker_command == COMMAND
        assert raised.value.return_code == client
        assert raised.value.stderr == "trunc"

    async def it_takes_a_client_exit_of_zero(
        state: dict[str, Any], container: Mock, run_result: Mock
    ) -> None:
        state["ExitCode"] = 0
        assert await agent_exit(container, 0, "") is run_result.return_value
        run_result.assert_called_once_with(0, oom_killed=False)

    async def it_reports_an_oom_kill(
        state: dict[str, Any], container: Mock, run_result: Mock
    ) -> None:
        state["OOMKilled"] = True
        assert await agent_exit(container, 125, "") is run_result.return_value
        run_result.assert_called_once_with(125, oom_killed=True)

    @pytest.mark.parametrize("record", [False, None, "true", 1])
    async def it_reports_no_oom_kill_without_a_true_record(
        state: dict[str, Any], container: Mock, run_result: Mock, record: object
    ) -> None:
        state["OOMKilled"] = record
        assert await agent_exit(container, 125, "") is run_result.return_value
        run_result.assert_called_once_with(125, oom_killed=False)

    @pytest.mark.parametrize("status", ["running", "created", "dead"])
    async def it_raises_with_the_client_when_the_container_never_exited(
        state: dict[str, Any], status: str, container: Mock
    ) -> None:
        state["Status"] = status
        with pytest.raises(DockerException) as raised:
            await agent_exit(container, -9, "lost the attach\n")
        assert raised.value.docker_command == COMMAND
        assert raised.value.return_code == -9
        assert raised.value.stderr == "lost the attach\n"

    @pytest.mark.parametrize("client", [125, -9])
    async def it_raises_with_the_client_when_the_container_cannot_be_inspected(
        inspect: AsyncMock, container: Mock, client: int
    ) -> None:
        inspect.side_effect = DockerException(["docker", "container", "inspect"], 1, "No such")
        with pytest.raises(DockerException) as raised:
            await agent_exit(container, client, "Cannot connect\n")
        assert raised.value.docker_command == COMMAND
        assert raised.value.return_code == client
        assert raised.value.stderr == "Cannot connect\n"
        assert raised.value.__suppress_context__
