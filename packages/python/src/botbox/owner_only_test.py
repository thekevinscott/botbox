from collections.abc import Iterator
from unittest.mock import Mock

import pytest

from botbox.owner_only import HELD, close_held, owner_only


@pytest.fixture(autouse=True)
def empty() -> Iterator[None]:
    HELD.clear()
    yield
    HELD.clear()


def describe_owner_only() -> None:
    def it_holds_the_pipe_only_inside_the_block() -> None:
        pipe = Mock()
        with owner_only(pipe):
            assert pipe in HELD
        assert pipe not in HELD

    def it_releases_the_pipe_when_the_block_raises() -> None:
        pipe = Mock()
        with pytest.raises(RuntimeError), owner_only(pipe):
            raise RuntimeError
        assert pipe not in HELD


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
