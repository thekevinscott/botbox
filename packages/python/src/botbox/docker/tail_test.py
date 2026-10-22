import asyncio

from botbox.docker.tail import tail


async def reader(data: bytes) -> asyncio.StreamReader:
    stream = asyncio.StreamReader()
    stream.feed_data(data)
    stream.feed_eof()
    return stream


def describe_tail() -> None:
    async def it_returns_everything_under_the_limit() -> None:
        assert await tail(await reader(b"short"), 10) == b"short"

    async def it_keeps_only_the_last_limit_bytes() -> None:
        assert await tail(await reader(b"a" * 100 + b"b" * 10), 10) == b"b" * 10

    async def it_reads_to_the_end_in_pieces_of_the_limit() -> None:
        assert await tail(await reader(b"abcdefghij"), 3) == b"hij"
