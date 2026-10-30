import asyncio
from pathlib import Path

import pytest

from botbox.utils.FileLines import FileLines


class Followed:
    """What `tail` follows: each line once it is fed, b"" once ended."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.pulls = 0

    def __aiter__(self) -> "Followed":
        return self

    async def __anext__(self) -> bytes:
        self.pulls += 1
        line = await self.queue.get()
        if not line:
            raise StopAsyncIteration
        return line


@pytest.fixture
def path(tmp_path: Path) -> Path:
    path = tmp_path / "stdout.txt"
    path.write_bytes(b"")
    return path


@pytest.fixture
def followed() -> Followed:
    return Followed()


@pytest.fixture
def lines(path: Path, followed: Followed) -> FileLines:
    return FileLines(path, followed)


def append(path: Path, data: bytes) -> None:
    with path.open("ab") as file:
        file.write(data)


def describe_FileLines() -> None:
    async def it_returns_lines_as_tail_follows_them(
        path: Path, followed: Followed, lines: FileLines
    ) -> None:
        append(path, b"one\ntwo\n")
        followed.queue.put_nowait(b"one\n")
        followed.queue.put_nowait(b"two\n")
        assert await lines.readline() == b"one\n"
        assert await lines.readline() == b"two\n"

    async def it_waits_for_the_next_line(followed: Followed, lines: FileLines) -> None:
        reading = asyncio.ensure_future(lines.readline())
        await asyncio.sleep(0.01)
        assert not reading.done()
        followed.queue.put_nowait(b"late\n")
        assert await reading == b"late\n"

    async def it_returns_the_unterminated_rest_then_nothing_once_ended(
        path: Path, followed: Followed, lines: FileLines
    ) -> None:
        append(path, b"a\nrest")
        followed.queue.put_nowait(b"a\n")
        lines.end()
        assert await lines.readline() == b"a\n"
        assert await lines.readline() == b"rest"
        assert await lines.readline() == b""
        assert await lines.readline() == b""

    async def it_reads_whole_lines_without_waiting_for_tail_once_ended(
        path: Path, lines: FileLines
    ) -> None:
        append(path, b"a\nb")
        lines.end()
        assert await lines.readline() == b"a\n"
        assert await lines.readline() == b"b"

    async def it_wakes_a_waiting_read_when_ended(lines: FileLines) -> None:
        reading = asyncio.ensure_future(lines.readline())
        await asyncio.sleep(0.01)
        lines.end()
        assert await reading == b""

    async def it_reads_what_was_written_before_it_ended(path: Path, lines: FileLines) -> None:
        reading = asyncio.ensure_future(lines.readline())
        await asyncio.sleep(0.01)
        append(path, b"last")
        lines.end()
        assert await reading == b"last"

    async def it_reads_written_lines_even_if_tail_ends_first(
        path: Path, followed: Followed, lines: FileLines
    ) -> None:
        append(path, b"a\n")
        reading = asyncio.ensure_future(lines.readline())
        await asyncio.sleep(0.01)
        followed.queue.put_nowait(b"")
        await asyncio.sleep(0.01)
        assert not reading.done()
        lines.end()
        assert await reading == b"a\n"
        assert await lines.readline() == b""

    async def it_loses_nothing_to_a_cancelled_read(followed: Followed, lines: FileLines) -> None:
        reading = asyncio.ensure_future(lines.readline())
        await asyncio.sleep(0.01)
        reading.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reading
        followed.queue.put_nowait(b"kept\n")
        assert await lines.readline() == b"kept\n"
        assert followed.pulls == 1

    async def it_stops_a_pending_pull_when_closed(lines: FileLines) -> None:
        reading = asyncio.ensure_future(lines.readline())
        await asyncio.sleep(0.01)
        reading.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reading
        assert lines.next is not None
        pending = lines.next
        await lines.close()
        assert pending.cancelled()

    async def it_closes_with_nothing_pending(lines: FileLines) -> None:
        await lines.close()
