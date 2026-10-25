from collections.abc import Iterator
from unittest.mock import Mock

import pytest

from botbox.posix_tools.process.close_held import HELD, close_held


@pytest.fixture(autouse=True)
def empty() -> Iterator[None]:
    HELD.clear()
    yield
    HELD.clear()


def describe_close_held() -> None:
    def it_closes_every_held_pipe_and_forgets_them() -> None:
        pipes = [Mock(), Mock()]
        HELD.update(pipes)
        close_held()
        for pipe in pipes:
            pipe.close.assert_called_once_with()
        assert not HELD

    def it_keeps_closing_past_a_pipe_that_fails() -> None:
        broken, ok = Mock(), Mock()
        broken.close.side_effect = OSError
        HELD.update([broken, ok])
        close_held()
        ok.close.assert_called_once_with()
        assert not HELD
