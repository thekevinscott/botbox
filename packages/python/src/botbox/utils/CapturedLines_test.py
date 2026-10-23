import asyncio
from unittest.mock import Mock

import pytest

from botbox.utils.CapturedLines import CapturedLines


@pytest.fixture
async def client() -> asyncio.Future[int]:
    return asyncio.get_running_loop().create_future()


@pytest.fixture
def capture() -> Mock:
    return Mock(into=bytearray(), grew=asyncio.Event())


@pytest.fixture
def reader(capture: Mock, client: asyncio.Future[int]) -> CapturedLines:
    return CapturedLines(capture, client)


def describe_CapturedLines() -> None:
    async def it_reads_complete_and_empty_lines_without_removing_captured_bytes(
        capture: Mock, reader: CapturedLines
    ) -> None:
        capture.into.extend(b"first\n\nsecond\n")
        assert await reader.readline() == b"first\n"
        assert await reader.readline() == b"\n"
        assert await reader.readline() == b"second\n"
        assert capture.into == b"first\n\nsecond\n"

    async def it_waits_for_a_partial_line_to_finish(capture: Mock, reader: CapturedLines) -> None:
        capture.into.extend(b"partial")
        reading = asyncio.create_task(reader.readline())
        await asyncio.sleep(0)
        assert not reading.done()
        capture.into.extend(b" line\n")
        capture.grew.set()
        assert await asyncio.wait_for(reading, 1) == b"partial line\n"

    async def it_wakes_on_exit_and_returns_the_unterminated_tail_then_eof(
        capture: Mock, client: asyncio.Future[int], reader: CapturedLines
    ) -> None:
        capture.into.extend(b"tail")
        reading = asyncio.create_task(reader.readline())
        await asyncio.sleep(0)
        client.set_result(3)
        assert await asyncio.wait_for(reading, 1) == b"tail"
        assert await reader.readline() == b""

    async def it_returns_eof_when_the_client_exits_without_output(
        client: asyncio.Future[int], reader: CapturedLines
    ) -> None:
        reading = asyncio.create_task(reader.readline())
        await asyncio.sleep(0)
        client.set_result(0)
        assert await asyncio.wait_for(reading, 1) == b""

    async def it_keeps_partial_bytes_when_a_read_is_cancelled(
        capture: Mock, reader: CapturedLines
    ) -> None:
        capture.into.extend(b"part")
        reading = asyncio.create_task(reader.readline())
        await asyncio.sleep(0)
        reading.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reading
        capture.into.extend(b"ial\n")
        assert await reader.readline() == b"partial\n"

    async def it_reads_large_lines_and_bytes_without_decoding(
        capture: Mock, reader: CapturedLines
    ) -> None:
        data = b"\xff" * 200_000 + b"\n"
        capture.into.extend(data)
        assert await reader.readline() == data
