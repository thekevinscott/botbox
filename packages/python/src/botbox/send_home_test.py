import asyncio
from unittest.mock import AsyncMock, Mock

from botbox.send_home import send_home


def writer(drain: AsyncMock) -> Mock:
    return Mock(spec=asyncio.StreamWriter, drain=drain)


def describe_send_home() -> None:
    async def it_writes_the_archive_and_waits_for_it_to_drain() -> None:
        stdin = writer(AsyncMock())
        await send_home(stdin, b"archive")
        stdin.write.assert_called_once_with(b"archive")
        stdin.drain.assert_awaited_once_with()

    async def it_writes_nothing_without_an_archive() -> None:
        stdin = writer(AsyncMock())
        await send_home(stdin, b"")
        stdin.write.assert_not_called()

    async def it_leaves_a_relay_that_died_first_to_its_exit_code() -> None:
        for error in (BrokenPipeError, ConnectionResetError):
            await send_home(writer(AsyncMock(side_effect=error)), b"archive")
