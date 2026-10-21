import io
from collections.abc import Iterator
from unittest.mock import MagicMock, Mock, patch

import pytest

from botbox.collect import collect


class DockerError(Exception):
    """Stands in for python_on_whales' DockerException."""


@pytest.fixture(autouse=True)
def docker_exception() -> Iterator[None]:
    with patch("botbox.collect.DockerException", DockerError):
        yield


@pytest.fixture(autouse=True)
def docker() -> Iterator[MagicMock]:
    with patch("botbox.collect.docker", autospec=True) as m:
        yield m


ARGV = ["docker", "run", "--rm", "an-image"]


def attach(stdout: bytes = b"out\n", stderr: bytes = b"err\n", exit_code: int = 0) -> Mock:
    return Mock(
        stdout=io.BytesIO(stdout),
        stderr=io.BytesIO(stderr),
        wait=Mock(return_value=exit_code),
    )


@pytest.fixture
def subprocess() -> Iterator[MagicMock]:
    with patch("botbox.collect.subprocess", autospec=True) as m:
        yield m


@pytest.fixture
def popen(subprocess: MagicMock) -> MagicMock:
    subprocess.Popen.return_value = attach()
    popen: MagicMock = subprocess.Popen
    return popen


def describe_collect() -> None:
    def it_runs_the_client_with_no_stdin(popen: MagicMock, subprocess: MagicMock) -> None:
        collect(ARGV)
        popen.assert_called_once_with(
            ARGV,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def it_separates_stdout_from_stderr(popen: MagicMock) -> None:
        popen.return_value = attach(b"a\nb\n", b"x\ny\n")
        assert collect(ARGV)[:2] == ("a\nb\n", "x\ny\n")

    def it_returns_the_attached_clients_exit_code(popen: MagicMock) -> None:
        popen.return_value = attach(exit_code=3)
        assert collect(ARGV) == ("out\n", "err\n", 3)

    def it_decodes_utf8(popen: MagicMock) -> None:
        popen.return_value = attach("é\n".encode(), b"")
        assert collect(ARGV)[0] == "é\n"

    def it_replaces_bytes_that_are_not_utf8(popen: MagicMock) -> None:
        popen.return_value = attach(b"\xff", b"\xfe")
        assert collect(ARGV)[:2] == ("�", "�")

    def it_drains_stderr_on_a_thread_that_cant_hold_up_exit(popen: MagicMock) -> None:  # noqa: ARG001
        with patch("botbox.collect.threading.Thread", autospec=True) as thread:
            collect(ARGV)
        assert thread.call_args.kwargs["daemon"] is True
        thread.return_value.start.assert_called_once_with()
        thread.return_value.join.assert_called_once_with()

    @pytest.mark.parametrize("exit_code", [1, 126])
    def it_does_not_ask_after_the_daemon_for_any_other_exit(
        popen: MagicMock, docker: MagicMock, exit_code: int
    ) -> None:
        popen.return_value = attach(exit_code=exit_code)
        assert collect(ARGV)[2] == exit_code
        docker.version.assert_not_called()

    def describe_when_the_client_exits_125() -> None:
        def it_reports_minus_one_when_the_daemon_is_gone(
            popen: MagicMock, docker: MagicMock
        ) -> None:
            popen.return_value = attach(b"half", b"warn", 125)
            docker.version.side_effect = DockerError("Cannot connect to the Docker daemon")
            assert collect(ARGV) == ("half", "warn", -1)

        def it_keeps_125_when_the_daemon_answers(popen: MagicMock, docker: MagicMock) -> None:
            popen.return_value = attach(exit_code=125)
            assert collect(ARGV)[2] == 125
            docker.version.assert_called_once_with()

    def describe_when_interrupted() -> None:
        def it_kills_the_client_and_reraises(popen: MagicMock) -> None:
            process = attach()
            process.wait.side_effect = [KeyboardInterrupt, 0]
            popen.return_value = process
            with pytest.raises(KeyboardInterrupt):
                collect(ARGV)
            process.kill.assert_called_once_with()
            assert process.wait.call_count == 2
