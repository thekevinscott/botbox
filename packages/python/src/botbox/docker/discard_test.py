import asyncio

from botbox.docker.discard import CHUNK, discard


def describe_discard() -> None:
    def it_reads_64k_at_a_time() -> None:
        assert CHUNK == 64 * 1024

    async def it_reads_the_stream_to_its_end() -> None:
        stream = asyncio.StreamReader()
        stream.feed_data(b"x" * 200_000)
        stream.feed_eof()
        await discard(stream)
        assert stream.at_eof()
