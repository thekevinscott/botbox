import asyncio
from unittest.mock import Mock

from botbox.docker.finish import finish


def describe_finish() -> None:
    async def it_stops_and_awaits_the_readers_still_reading() -> None:
        reading = asyncio.ensure_future(asyncio.Event().wait())
        await finish(Mock(), (reading,))
        assert reading.cancelled()

    async def it_leaves_finished_readers_as_they_are() -> None:
        async def read() -> None:
            pass

        done = asyncio.ensure_future(read())
        await done
        await finish(Mock(), (done,))
        assert not done.cancelled()

    async def it_swallows_a_failed_reader() -> None:
        async def read() -> None:
            raise OSError("pipe broke")

        await finish(Mock(), (asyncio.ensure_future(read()),))

    async def it_closes_the_pipes_to_the_process() -> None:
        process = Mock()
        await finish(process, ())
        process._transport.close.assert_called_once_with()
