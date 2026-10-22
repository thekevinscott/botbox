from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from botbox.docker.remove import remove


@pytest.fixture
def run_docker() -> Iterator[AsyncMock]:
    with patch("botbox.docker.remove.run_docker", autospec=True) as m:
        yield m


def describe_remove() -> None:
    async def it_force_removes_the_container(run_docker: AsyncMock) -> None:
        assert await remove("sdk-box") is None
        run_docker.assert_awaited_once_with("rm", "--force", "sdk-box")
