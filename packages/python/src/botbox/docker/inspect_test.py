from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from botbox.docker.inspect import inspect


@pytest.fixture(autouse=True)
def run_docker() -> Iterator[AsyncMock]:
    with patch("botbox.docker.inspect.run_docker", autospec=True) as m:
        m.return_value = '[{"Name":"/sdk-box","State":{"Status":"exited","ExitCode":5}}]\n'
        yield m


def describe_inspect() -> None:
    async def it_asks_for_the_container_as_json(run_docker: AsyncMock) -> None:
        await inspect("sdk-box")
        run_docker.assert_awaited_once_with("container", "inspect", "--format", "json", "sdk-box")

    async def it_returns_the_one_container() -> None:
        assert await inspect("sdk-box") == {
            "Name": "/sdk-box",
            "State": {"Status": "exited", "ExitCode": 5},
        }
