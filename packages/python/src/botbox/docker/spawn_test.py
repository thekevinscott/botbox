import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from botbox.docker.spawn import spawn


@pytest.fixture
def exec_() -> Iterator[AsyncMock]:
    with patch("botbox.docker.spawn.asyncio.create_subprocess_exec", autospec=True) as m:
        yield m


def describe_spawn() -> None:
    async def it_takes_its_streams_by_keyword_only(exec_: AsyncMock) -> None:
        with pytest.raises(TypeError):
            await spawn([], None, None, None)  # type: ignore[misc]

    async def it_runs_docker_with_the_args_in_a_session_of_its_own(exec_: AsyncMock) -> None:
        await spawn(
            ["version", "--format", "json"],
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=None,
        )
        exec_.assert_awaited_once_with(
            "docker",
            "version",
            "--format",
            "json",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=None,
            start_new_session=True,
        )

    async def it_returns_the_process(exec_: AsyncMock) -> None:
        assert await spawn([], stdin=None, stdout=None, stderr=None) is exec_.return_value
