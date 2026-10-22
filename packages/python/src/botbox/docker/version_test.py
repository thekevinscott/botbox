from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from botbox.docker.version import version


@pytest.fixture(autouse=True)
def run_docker() -> Iterator[AsyncMock]:
    with patch("botbox.docker.version.run_docker", autospec=True) as m:
        m.return_value = '{"Client":{"Version":"29.1"},"Server":{"Version":"29.1"}}\n'
        yield m


def describe_version() -> None:
    async def it_asks_for_json(run_docker: AsyncMock) -> None:
        await version()
        run_docker.assert_awaited_once_with("version", "--format", "json")

    async def it_parses_the_client_and_server() -> None:
        assert await version() == {
            "Client": {"Version": "29.1"},
            "Server": {"Version": "29.1"},
        }
