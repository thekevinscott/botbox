from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from adocker.inspect_image import inspect_image


@pytest.fixture(autouse=True)
def run_docker() -> Iterator[AsyncMock]:
    with patch("adocker.inspect_image.run_docker", autospec=True) as m:
        m.return_value = '[{"Id":"sha256:abc","RepoTags":["sdk:latest"]}]\n'
        yield m


def describe_inspect_image() -> None:
    async def it_asks_for_the_image_as_json(run_docker: AsyncMock) -> None:
        await inspect_image("sdk:latest")
        run_docker.assert_awaited_once_with("image", "inspect", "--format", "json", "sdk:latest")

    async def it_returns_the_one_image() -> None:
        assert await inspect_image("sdk:latest") == {"Id": "sha256:abc", "RepoTags": ["sdk:latest"]}
