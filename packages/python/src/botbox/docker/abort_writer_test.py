import asyncio
import os
from collections.abc import AsyncIterator
from unittest.mock import Mock

import pytest

from botbox.docker.abort_writer import abort_writer


@pytest.fixture
async def writer() -> AsyncIterator[asyncio.StreamWriter]:
    """A writer on a real pipe whose read end is held open and never read."""
    read, write = os.pipe()
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.connect_write_pipe(
        asyncio.streams.FlowControlMixin, os.fdopen(write, "wb")
    )
    yield asyncio.StreamWriter(transport, protocol, None, loop)
    if not transport.is_closing():
        transport.abort()
    await asyncio.sleep(0)
    os.close(read)


def fake(closing: bool, buffered: int) -> Mock:
    return Mock(
        transport=Mock(
            is_closing=Mock(return_value=closing), get_write_buffer_size=Mock(return_value=buffered)
        )
    )


def describe_abort_writer() -> None:
    async def it_aborts_an_open_writer(writer: asyncio.StreamWriter) -> None:
        abort_writer(writer)
        assert writer.transport.is_closing()
        await asyncio.sleep(0)
        assert writer.transport.get_extra_info("pipe").closed

    async def it_drops_input_still_buffered_after_a_close(writer: asyncio.StreamWriter) -> None:
        writer.write(b"x" * 1_000_000)
        writer.close()
        abort_writer(writer)
        assert writer.transport.get_write_buffer_size() == 0

    async def it_leaves_a_writer_that_has_already_closed(writer: asyncio.StreamWriter) -> None:
        writer.close()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        abort_writer(writer)
        abort_writer(writer)
        await asyncio.sleep(0)

    def it_aborts_unless_closing_with_nothing_left_to_send() -> None:
        for closing, buffered, aborts in [(False, 0, True), (True, 3, True), (True, 0, False)]:
            writer = fake(closing, buffered)
            abort_writer(writer)
            assert writer.transport.abort.called is aborts
