from collections.abc import Iterator
from unittest.mock import Mock, patch

import pytest

from botbox.linux_tools.process.group_running import group_running


def stat(text: str) -> Mock:
    return Mock(read_text=Mock(return_value=text))


def vanished() -> Mock:
    return Mock(read_text=Mock(side_effect=FileNotFoundError))


@pytest.fixture
def proc() -> Iterator[Mock]:
    with patch("botbox.linux_tools.process.group_running.Path", autospec=True) as m:
        yield m.return_value.glob


def describe_group_running() -> None:
    def it_reads_every_process_status(proc: Mock) -> None:
        proc.return_value = []
        group_running(4242)
        proc.assert_called_once_with("[0-9]*/stat")

    def it_finds_a_running_member(proc: Mock) -> None:
        proc.return_value = [stat("4243 (docker-buildx) S 1 4242 4242 0")]
        assert group_running(4242) is True

    def it_ignores_other_groups(proc: Mock) -> None:
        proc.return_value = [
            stat("4243 (docker-buildx) S 1 4241 4241 0"),
            stat("4244 (docker-buildx) S 1 4243 4243 0"),
        ]
        assert group_running(4242) is False

    def it_does_not_count_zombies_or_the_dead(proc: Mock) -> None:
        proc.return_value = [stat("4243 (a) Z 1 4242 4242 0"), stat("4244 (b) X 1 4242 4242 0")]
        assert group_running(4242) is False

    def it_reads_past_a_name_with_spaces_and_parentheses(proc: Mock) -> None:
        proc.return_value = [stat("4243 (a) S 1 9 (b) R 1 4242 4242 0")]
        assert group_running(4242) is True

    def it_skips_a_process_gone_while_reading(proc: Mock) -> None:
        proc.return_value = [vanished(), stat("4243 (a) R 1 4242 4242 0")]
        assert group_running(4242) is True
