import asyncio
from collections.abc import Iterator
from unittest.mock import Mock, call, patch

import pytest

from botbox.posix_tools.process.exit_code import POLL, exit_code


@pytest.fixture
def sleep() -> Iterator[Mock]:
    with patch(
        "botbox.posix_tools.process.exit_code.asyncio.sleep", side_effect=asyncio.sleep
    ) as m:
        yield m


def describe_exit_code() -> None:
    def it_polls_every_10ms() -> None:
        assert POLL == 0.01

    async def it_returns_a_code_already_known(sleep: Mock) -> None:
        assert await exit_code(Mock(returncode=3)) == 3
        sleep.assert_not_called()

    async def it_waits_for_asyncio_to_record_the_code(sleep: Mock) -> None:
        process = Mock(returncode=None)
        asyncio.get_running_loop().call_later(0.03, setattr, process, "returncode", 0)
        assert await exit_code(process) == 0
        assert sleep.call_args_list
        assert all(c == call(POLL) for c in sleep.call_args_list)
