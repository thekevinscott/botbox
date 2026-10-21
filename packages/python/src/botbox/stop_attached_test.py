from collections.abc import Iterator
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from botbox.stop_attached import stop_attached


class Timeout(Exception):
    """Stands in for subprocess.TimeoutExpired."""


@pytest.fixture(autouse=True)
def timeout_expired() -> Iterator[MagicMock]:
    with patch("botbox.stop_attached.subprocess") as m:
        m.TimeoutExpired = Timeout
        yield m


@pytest.fixture
def process() -> Mock:
    process = Mock()
    process.wait.return_value = 0
    return process


@pytest.fixture
def stdin() -> Mock:
    return Mock()


def describe_stop_attached() -> None:
    def it_closes_stdin_then_waits_with_a_bound(process: Mock, stdin: Mock) -> None:
        manager = Mock()
        manager.attach_mock(stdin, "stdin")
        manager.attach_mock(process, "process")
        stop_attached(process, stdin, 10)
        assert manager.mock_calls == [call.stdin.close(), call.process.wait(timeout=10)]

    def it_kills_the_attach_when_it_outlives_the_bound(process: Mock, stdin: Mock) -> None:
        process.wait.side_effect = [Timeout(), 0]
        stop_attached(process, stdin, 10)
        process.kill.assert_called_once_with()
        assert process.wait.call_args_list == [call(timeout=10), call()]

    def it_still_waits_when_stdin_is_already_closed(process: Mock, stdin: Mock) -> None:
        stdin.close.side_effect = BrokenPipeError
        stop_attached(process, stdin, 10)
        process.wait.assert_called_once_with(timeout=10)
