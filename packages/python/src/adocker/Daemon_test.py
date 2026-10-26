from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from adocker.Daemon import Daemon


@pytest.fixture
def run_docker() -> Iterator[AsyncMock]:
    with patch("adocker.Daemon.run_docker", autospec=True) as m:
        yield m


def describe_Daemon() -> None:
    async def it_parses_the_version_json(run_docker: AsyncMock) -> None:
        run_docker.return_value = '{"Server": {"Version": "29"}}'
        assert await Daemon().version() == {"Server": {"Version": "29"}}
        run_docker.assert_awaited_once_with("version", "--format", "json")
