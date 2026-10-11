from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from botbox.collect import collect


class DockerError(Exception):
    """Stands in for python_on_whales' DockerException."""


GONE = DockerError("Cannot connect to the Docker daemon")


@pytest.fixture(autouse=True)
def docker_exception() -> Iterator[None]:
    with patch("botbox.collect.DockerException", DockerError):
        yield


@pytest.fixture
def docker() -> Iterator[MagicMock]:
    with patch("botbox.collect.docker", autospec=True) as m:
        m.logs.return_value = iter([("stdout", b"out\n"), ("stderr", b"err\n")])
        m.wait.return_value = 0
        yield m


def dies_after(*chunks: tuple[str, bytes]) -> Iterator[tuple[str, bytes]]:
    yield from chunks
    raise GONE


def describe_collect() -> None:
    def it_follows_the_containers_output_as_it_streams(docker: MagicMock) -> None:
        collect("c")
        docker.logs.assert_called_once_with("c", follow=True, stream=True)

    def it_separates_stdout_from_stderr(docker: MagicMock) -> None:
        docker.logs.return_value = iter(
            [("stdout", b"a"), ("stderr", b"x"), ("stdout", b"b"), ("stderr", b"y")]
        )
        assert collect("c")[:2] == ("ab", "xy")

    def it_waits_for_the_exit_code(docker: MagicMock) -> None:
        docker.wait.return_value = 3
        assert collect("c") == ("out\n", "err\n", 3)
        docker.wait.assert_called_once_with("c")

    def it_decodes_utf8(docker: MagicMock) -> None:
        e = "é".encode()
        docker.logs.return_value = iter([("stdout", e[:1]), ("stdout", e[1:])])
        assert collect("c")[0] == "é"

    def it_replaces_bytes_that_are_not_utf8(docker: MagicMock) -> None:
        docker.logs.return_value = iter([("stdout", b"\xff"), ("stderr", b"\xfe")])
        assert collect("c")[:2] == ("�", "�")

    def describe_when_the_daemon_dies() -> None:
        def it_keeps_what_arrived_and_reports_minus_one(docker: MagicMock) -> None:
            docker.logs.return_value = dies_after(("stdout", b"half"), ("stderr", b"warn"))
            assert collect("c") == ("half", "warn", -1)

        def it_does_not_wait_on_a_dead_daemon(docker: MagicMock) -> None:
            docker.logs.return_value = dies_after()
            collect("c")
            docker.wait.assert_not_called()

        def it_reports_minus_one_when_the_wait_fails(docker: MagicMock) -> None:
            docker.wait.side_effect = GONE
            assert collect("c") == ("out\n", "err\n", -1)

        def it_reports_minus_one_when_the_container_cannot_be_followed(
            docker: MagicMock,
        ) -> None:
            docker.logs.side_effect = GONE
            assert collect("c") == ("", "", -1)

    def it_lets_an_interrupt_through(docker: MagicMock) -> None:
        docker.logs.side_effect = KeyboardInterrupt
        with pytest.raises(KeyboardInterrupt):
            collect("c")
