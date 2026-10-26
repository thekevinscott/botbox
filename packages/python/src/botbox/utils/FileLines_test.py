import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import IO

import pytest

from botbox.utils.FileLines import FileLines


@pytest.fixture
def path(tmp_path: Path) -> Path:
    path = tmp_path / "stdout.txt"
    path.write_bytes(b"")
    return path


@pytest.fixture
def appender(path: Path) -> Iterator[IO[bytes]]:
    with path.open("ab", buffering=0) as file:
        yield file


@pytest.fixture
def lines(path: Path) -> Iterator[FileLines]:
    with path.open("rb") as file:
        yield FileLines(file)


def describe_FileLines() -> None:
    async def it_reads_lines_already_written(appender: IO[bytes], lines: FileLines) -> None:
        appender.write(b"one\ntwo\n")
        assert await lines.readline() == b"one\n"
        assert await lines.readline() == b"two\n"

    async def it_waits_for_a_line_to_be_finished(appender: IO[bytes], lines: FileLines) -> None:
        appender.write(b"par")
        reading = asyncio.ensure_future(lines.readline())
        await asyncio.sleep(0.01)
        assert not reading.done()
        appender.write(b"tial\n")
        lines.grew()
        assert await reading == b"partial\n"

    async def it_returns_the_unterminated_rest_then_nothing_once_ended(
        appender: IO[bytes], lines: FileLines
    ) -> None:
        appender.write(b"a\nrest")
        lines.end()
        assert await lines.readline() == b"a\n"
        assert await lines.readline() == b"rest"
        assert await lines.readline() == b""
        assert await lines.readline() == b""

    async def it_wakes_a_waiting_read_when_ended(lines: FileLines) -> None:
        reading = asyncio.ensure_future(lines.readline())
        await asyncio.sleep(0.01)
        lines.end()
        assert await reading == b""

    async def it_reads_what_was_written_before_it_ended(
        appender: IO[bytes], lines: FileLines
    ) -> None:
        reading = asyncio.ensure_future(lines.readline())
        await asyncio.sleep(0.01)
        appender.write(b"last")
        lines.end()
        assert await reading == b"last"

    async def it_loses_nothing_to_a_cancelled_read(appender: IO[bytes], lines: FileLines) -> None:
        appender.write(b"half")
        reading = asyncio.ensure_future(lines.readline())
        await asyncio.sleep(0.01)
        reading.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reading
        appender.write(b" line\n")
        lines.grew()
        assert await lines.readline() == b"half line\n"
