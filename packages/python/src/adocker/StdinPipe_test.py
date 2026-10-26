import asyncio
import os
from collections.abc import Iterator
from pathlib import Path
from typing import IO
from unittest.mock import Mock, patch

import pytest

from adocker.StdinPipe import HELD, StdinPipe, close_held


def open_fds() -> set[str]:
    return {fd.name for fd in Path("/proc/self/fd").iterdir()}


@pytest.fixture(autouse=True)
def held() -> Iterator[set[IO[bytes]]]:
    HELD.clear()
    yield HELD
    HELD.clear()


def describe_StdinPipe() -> None:
    async def it_writes_through_to_its_read_end() -> None:
        pipe = await StdinPipe.open()
        pipe.writer.write(b"hello")
        await pipe.writer.drain()
        assert os.read(pipe.read, 5) == b"hello"
        pipe.writer.close()
        pipe.release()

    async def it_holds_its_write_end_until_released(held: set[IO[bytes]]) -> None:
        pipe = await StdinPipe.open()
        assert held == {pipe.pipe}
        pipe.release()
        assert not held
        pipe.writer.close()

    async def it_closes_the_read_end_once_released() -> None:
        pipe = await StdinPipe.open()
        pipe.release()
        with pytest.raises(OSError):
            os.fstat(pipe.read)
        pipe.writer.close()

    async def it_closes_both_ends_when_it_cannot_watch_the_pipe(held: set[IO[bytes]]) -> None:
        before = open_fds()
        loop = asyncio.get_running_loop()
        with (
            patch.object(loop, "connect_write_pipe", side_effect=OSError("no watch")),
            pytest.raises(OSError, match="no watch"),
        ):
            await StdinPipe.open()
        assert open_fds() <= before
        assert not held


def describe_close_held() -> None:
    def it_closes_every_held_pipe_and_forgets_them(held: set[IO[bytes]]) -> None:
        pipes = [Mock(), Mock()]
        held.update(pipes)
        close_held()
        for pipe in pipes:
            pipe.close.assert_called_once_with()
        assert not held

    def it_keeps_closing_past_a_pipe_that_fails(held: set[IO[bytes]]) -> None:
        broken, ok = Mock(), Mock()
        broken.close.side_effect = OSError
        held.update([broken, ok])
        close_held()
        ok.close.assert_called_once_with()
        assert not held
