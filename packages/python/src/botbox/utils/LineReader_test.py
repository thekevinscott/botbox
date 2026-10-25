import asyncio

import pytest

from botbox.utils.LineReader import LineReader


def describe_LineReader() -> None:
    @pytest.mark.parametrize("size", [0, 7, 8, 9, 200_000])
    @pytest.mark.parametrize("ending", [b"", b"\n"])
    async def it_preserves_lines_and_eof(size: int, ending: bytes) -> None:
        stream = asyncio.StreamReader(limit=8)
        reader = LineReader(stream)
        line = b"x" * size + ending
        stream.feed_data(line)
        stream.feed_eof()
        assert await reader.readline() == line
        assert reader.at_eof()
        assert await reader.readline() == b""

    async def it_preserves_boundaries_across_chunks() -> None:
        stream = asyncio.StreamReader(limit=8)
        reader = LineReader(stream)
        stream.feed_data(b"a" * 30 + b"\nshort\nlast")
        stream.feed_eof()
        assert await reader.readline() == b"a" * 30 + b"\n"
        assert not reader.at_eof()
        assert await reader.readline() == b"short\n"
        assert await reader.readline() == b"last"
        assert reader.at_eof()

    async def it_keeps_consumed_chunks_when_a_read_is_cancelled() -> None:
        stream = asyncio.StreamReader(limit=8)
        reader = LineReader(stream)
        stream.feed_data(b"a" * 30)
        task = asyncio.create_task(reader.readline())
        await asyncio.sleep(0)
        assert not task.done()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        stream.feed_eof()
        assert not reader.at_eof()
        assert await reader.readline() == b"a" * 30
        assert reader.at_eof()

    async def it_reads_a_line_arriving_in_separate_chunks() -> None:
        stream = asyncio.StreamReader(limit=8)
        reader = LineReader(stream)
        task = asyncio.create_task(reader.readline())
        for chunk in [b"a" * 20, b"b" * 20, b"c\nnext\n"]:
            stream.feed_data(chunk)
            await asyncio.sleep(0)
        assert await task == b"a" * 20 + b"b" * 20 + b"c\n"
        assert await reader.readline() == b"next\n"
