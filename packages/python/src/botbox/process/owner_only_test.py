from collections.abc import Iterator
from typing import IO
from unittest.mock import Mock, patch

import pytest

from botbox.process.owner_only import owner_only


@pytest.fixture(autouse=True)
def held() -> Iterator[set[IO[bytes]]]:
    pipes: set[IO[bytes]] = set()
    with patch("botbox.process.owner_only.HELD", pipes):
        yield pipes


def describe_owner_only() -> None:
    def it_holds_the_pipe_only_inside_the_block(held: set[IO[bytes]]) -> None:
        pipe = Mock()
        with owner_only(pipe):
            assert pipe in held
        assert pipe not in held

    def it_releases_the_pipe_when_the_block_raises(held: set[IO[bytes]]) -> None:
        pipe = Mock()
        with pytest.raises(RuntimeError), owner_only(pipe):
            raise RuntimeError
        assert pipe not in held
