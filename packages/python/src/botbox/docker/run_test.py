import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from botbox.docker.run import run


@pytest.fixture
def spawn() -> Iterator[AsyncMock]:
    with patch("botbox.docker.run.spawn", autospec=True) as m:
        yield m


def describe_run() -> None:
    @pytest.mark.usefixtures("spawn")
    async def it_takes_its_streams_by_keyword_only() -> None:
        with pytest.raises(TypeError):
            await run([], None, None, None)  # type: ignore[call-arg]

    async def it_runs_attached_with_the_streams_it_is_given(spawn: AsyncMock) -> None:
        await run(
            ["--interactive", "busybox", "cat"],
            stdin=7,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        spawn.assert_awaited_once_with(
            ["run", "--interactive", "busybox", "cat"],
            stdin=7,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

    async def it_returns_the_process(spawn: AsyncMock) -> None:
        assert await run([], stdin=None, stdout=None, stderr=None) is spawn.return_value
