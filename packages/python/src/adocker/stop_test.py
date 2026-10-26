from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from adocker.stop import stop


@pytest.fixture
def run_docker() -> Iterator[AsyncMock]:
    with patch("adocker.stop.run_docker", autospec=True) as m:
        yield m


def describe_stop() -> None:
    async def it_stops_the_container_within_the_given_seconds(run_docker: AsyncMock) -> None:
        await stop("sdk-box", 5)
        run_docker.assert_awaited_once_with("stop", "--time", "5", "sdk-box")
