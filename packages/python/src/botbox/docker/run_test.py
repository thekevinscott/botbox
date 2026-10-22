from collections.abc import Iterator
from types import TracebackType
from unittest.mock import AsyncMock, Mock, patch

import pytest

from botbox.docker.run import run

KILL = 9


class Capture:
    """A fake capture that records what it fills, its limit, and whether it was left."""

    def __init__(self, into: bytearray, limit: int | None = None) -> None:
        self.into = into
        self.limit = limit
        self.closed = False
        MADE.append(self)

    async def __aenter__(self) -> "Capture":
        return self

    async def __aexit__(
        self,
        _type: type[BaseException] | None,
        _error: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        self.closed = True


MADE: list[Capture] = []


@pytest.fixture(autouse=True)
def captures() -> Iterator[list[Capture]]:
    MADE.clear()
    with patch("botbox.docker.run.Capture", Capture):
        yield MADE


@pytest.fixture(autouse=True)
def signal() -> Iterator[Mock]:
    with patch("botbox.docker.run.signal", autospec=True) as m:
        m.SIGKILL = KILL
        yield m


@pytest.fixture(autouse=True)
def execute() -> Iterator[AsyncMock]:
    with patch("botbox.docker.run.execute", autospec=True, return_value=5) as m:
        yield m


def describe_run() -> None:
    async def it_takes_its_streams_by_keyword_only() -> None:
        with pytest.raises(TypeError):
            await run([], None, bytearray(), bytearray())  # type: ignore[call-arg]

    async def it_runs_attached_on_its_stdin_into_captures_of_the_buffers_given(
        execute: AsyncMock, captures: list[Capture]
    ) -> None:
        out, err = bytearray(), bytearray()
        await run(["--interactive", "busybox", "cat"], stdin=7, stdout=out, stderr=err)
        stdout, stderr = captures
        assert stdout.into is out
        assert stderr.into is err
        execute.assert_awaited_once_with(
            ["run", "--interactive", "busybox", "cat"],
            stdin=7,
            stdout=stdout,
            stderr=stderr,
            signum=KILL,
        )

    async def it_keeps_all_the_output_by_default(captures: list[Capture]) -> None:
        await run([], stdin=None, stdout=bytearray(), stderr=bytearray())
        assert [capture.limit for capture in captures] == [None, None]

    async def it_keeps_the_end_of_each_stream_given_a_limit(captures: list[Capture]) -> None:
        await run([], stdin=None, stdout=bytearray(), stderr=bytearray(), limit=64)
        assert [capture.limit for capture in captures] == [64, 64]

    async def it_returns_the_clients_exit_code() -> None:
        assert await run([], stdin=None, stdout=bytearray(), stderr=bytearray()) == 5

    async def it_closes_the_captures_when_cancelled_or_failing(
        execute: AsyncMock, captures: list[Capture]
    ) -> None:
        execute.side_effect = OSError("wait failed")
        with pytest.raises(OSError, match="wait failed"):
            await run([], stdin=None, stdout=bytearray(), stderr=bytearray())
        assert all(capture.closed for capture in captures)
