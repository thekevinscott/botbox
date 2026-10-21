from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from botbox.wait_for_socket import wait_for_socket


@pytest.fixture
def clock() -> Iterator[MagicMock]:
    with patch("botbox.wait_for_socket.time", autospec=True) as m:
        m.monotonic.return_value = 0
        yield m


@pytest.fixture
def process() -> Mock:
    process = Mock()
    process.poll.return_value = None
    return process


@pytest.fixture
def output(tmp_path: Path) -> Path:
    output = tmp_path / "proxy.out"
    output.write_text("tinyproxy: bad config\n")
    return output


def describe_wait_for_socket() -> None:
    def it_returns_at_once_when_the_socket_is_there(
        tmp_path: Path, process: Mock, output: Path, clock: MagicMock
    ) -> None:
        socket = tmp_path / "proxy.sock"
        socket.touch()
        wait_for_socket(socket, process, output, 30)
        clock.sleep.assert_not_called()

    def it_polls_until_the_socket_appears(
        tmp_path: Path, process: Mock, output: Path, clock: MagicMock
    ) -> None:
        socket = tmp_path / "proxy.sock"
        clock.sleep.side_effect = lambda _s: socket.touch()
        wait_for_socket(socket, process, output, 30)
        clock.sleep.assert_called_once_with(0.05)

    def it_raises_with_the_output_when_the_process_exits_first(
        tmp_path: Path,
        process: Mock,
        output: Path,
        clock: MagicMock,  # noqa: ARG001
    ) -> None:
        process.poll.return_value = 1
        with pytest.raises(RuntimeError, match="did not start:\ntinyproxy: bad config"):
            wait_for_socket(tmp_path / "proxy.sock", process, output, 30)

    def it_raises_once_the_timeout_passes(
        tmp_path: Path, process: Mock, output: Path, clock: MagicMock
    ) -> None:
        clock.monotonic.side_effect = [100.0, 129.0, 130.0, 130.5]
        with pytest.raises(RuntimeError, match="tinyproxy: bad config"):
            wait_for_socket(tmp_path / "proxy.sock", process, output, 30)
        assert clock.sleep.call_count == 2
