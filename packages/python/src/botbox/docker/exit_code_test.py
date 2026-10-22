import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from botbox.docker.ended import POLL
from botbox.docker.exit_code import exit_code


@pytest.fixture(autouse=True)
def leader_exit() -> Iterator[AsyncMock]:
    with patch("botbox.docker.exit_code.leader_exit", autospec=True) as m:
        yield m


@pytest.fixture
def sleep() -> Iterator[Mock]:
    with patch("botbox.docker.exit_code.asyncio.sleep", side_effect=asyncio.sleep) as m:
        yield m


def describe_exit_code() -> None:
    async def it_returns_a_code_already_known(leader_exit: AsyncMock) -> None:
        assert await exit_code(Mock(pid=4242, returncode=3)) == 3
        leader_exit.assert_not_awaited()

    async def it_waits_for_the_leader_then_for_asyncio_to_record_its_code(
        leader_exit: AsyncMock, sleep: Mock
    ) -> None:
        process = Mock(pid=4242, returncode=None)
        asyncio.get_running_loop().call_later(0.03, setattr, process, "returncode", 0)
        assert await exit_code(process) == 0
        leader_exit.assert_awaited_once_with(4242)
        assert set(sleep.call_args_list) == {call(POLL)}
