from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from botbox.docker.wait import wait


@pytest.fixture(autouse=True)
def run_docker() -> Iterator[AsyncMock]:
    with patch("botbox.docker.wait.run_docker", autospec=True) as m:
        m.return_value = "137\n"
        yield m


def describe_wait() -> None:
    async def it_waits_for_the_container(run_docker: AsyncMock) -> None:
        await wait("sdk-box")
        run_docker.assert_awaited_once_with("wait", "sdk-box")

    async def it_returns_the_exit_code() -> None:
        assert await wait("sdk-box") == 137
