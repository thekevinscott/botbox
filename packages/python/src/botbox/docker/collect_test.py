import asyncio

import pytest

from botbox.docker.collect import collect


def stream(data: bytes, *, eof: bool = True) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    if eof:
        reader.feed_eof()
    return reader


def describe_collect() -> None:
    async def it_reads_the_stream_to_its_end_into_the_buffer() -> None:
        into = bytearray(b"kept ")
        await collect(stream(b"everything"), into)
        assert into == b"kept everything"

    async def it_keeps_only_the_last_limit_bytes() -> None:
        into = bytearray()
        await collect(stream(b"a" * 100 + b"b" * 10), into, 10)
        assert into == b"b" * 10

    async def it_reads_in_pieces_of_the_limit() -> None:
        into = bytearray()
        await collect(stream(b"abcdefghij"), into, 3)
        assert into == b"hij"

    async def it_keeps_nothing_with_a_limit_of_zero() -> None:
        into = bytearray()
        await collect(stream(b"discarded"), into, 0)
        assert into == b""

    async def it_leaves_what_it_read_when_cancelled_before_the_end() -> None:
        into = bytearray()
        reading = asyncio.ensure_future(collect(stream(b"partial", eof=False), into))
        await asyncio.sleep(0.01)
        reading.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reading
        assert into == b"partial"
