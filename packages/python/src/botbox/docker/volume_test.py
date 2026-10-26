from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from botbox.docker.volume import create_volume, remove_volume


@pytest.fixture
def run_docker() -> Iterator[AsyncMock]:
    with patch("botbox.docker.volume.run_docker", autospec=True) as m:
        yield m


def describe_create_volume() -> None:
    async def it_creates_a_labelled_named_volume(run_docker: AsyncMock) -> None:
        await create_volume("botbox-run-x", "botbox.run=x")
        run_docker.assert_awaited_once_with(
            "volume", "create", "--label", "botbox.run=x", "botbox-run-x"
        )


def describe_remove_volume() -> None:
    async def it_removes_the_volume(run_docker: AsyncMock) -> None:
        await remove_volume("botbox-run-x")
        run_docker.assert_awaited_once_with("volume", "rm", "--force", "botbox-run-x")
