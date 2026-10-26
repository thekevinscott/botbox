import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from adocker.remove_volume import remove_volume


@pytest.fixture
def run_docker() -> Iterator[AsyncMock]:
    with patch("adocker.remove_volume.run_docker", autospec=True) as m:
        yield m


def describe_remove_volume() -> None:
    async def it_force_removes_the_volume(run_docker: AsyncMock) -> None:
        await remove_volume("v", 30)
        run_docker.assert_awaited_once_with("volume", "rm", "--force", "v")

    async def it_gives_up_once_the_daemon_takes_too_long(run_docker: AsyncMock) -> None:
        async def slow(*_: str) -> str:
            await asyncio.sleep(3600)
            return ""

        run_docker.side_effect = slow
        with pytest.raises(TimeoutError, match=r"^the daemon did not remove it within 0\.01s$"):
            await remove_volume("v", 0.01)

    async def it_lets_other_failures_through(run_docker: AsyncMock) -> None:
        run_docker.side_effect = RuntimeError("in use")
        with pytest.raises(RuntimeError, match="in use"):
            await remove_volume("v", 30)
