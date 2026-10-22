import asyncio

from botbox.docker.discard import discard


def describe_discard() -> None:
    async def it_reads_the_stream_to_its_end() -> None:
        stream = asyncio.StreamReader()
        stream.feed_data(b"x" * 200_000)
        stream.feed_eof()
        await discard(stream)
        assert stream.at_eof()
