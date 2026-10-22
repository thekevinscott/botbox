import asyncio

from botbox.docker.harvest import harvest


async def finished(value: bytes) -> asyncio.Future[bytes]:
    future: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
    future.set_result(value)
    return future


def describe_harvest() -> None:
    async def it_returns_what_a_finished_drain_read() -> None:
        assert harvest(await finished(b"out")) == b"out"

    async def it_cancels_an_unfinished_drain_and_returns_nothing() -> None:
        drain: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
        assert harvest(drain) == b""
        assert drain.cancelled()

    async def it_returns_nothing_for_a_cancelled_drain() -> None:
        drain: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
        drain.cancel()
        assert harvest(drain) == b""

    async def it_returns_nothing_for_a_failed_drain() -> None:
        drain: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
        drain.set_exception(OSError("pipe broke"))
        assert harvest(drain) == b""
