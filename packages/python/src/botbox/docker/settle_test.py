import asyncio

import pytest

from botbox.docker.settle import settle


async def slow(seconds: float, value: str = "done") -> str:
    await asyncio.sleep(seconds)
    return value


def describe_settle() -> None:
    async def it_returns_what_the_coroutine_returns() -> None:
        assert await settle(slow(0)) == "done"

    async def it_propagates_what_the_coroutine_raises() -> None:
        async def fail() -> None:
            raise ValueError("teardown failed")

        with pytest.raises(ValueError, match="teardown failed"):
            await settle(fail())

    async def it_finishes_the_coroutine_through_repeated_cancels_then_raises_once() -> None:
        finished = asyncio.Event()

        async def teardown() -> None:
            await asyncio.sleep(0.05)
            finished.set()

        task = asyncio.create_task(settle(teardown()))
        for _ in range(3):
            await asyncio.sleep(0.01)
            task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()

    async def it_raises_when_the_coroutine_itself_is_cancelled() -> None:
        async def cancelled() -> None:
            raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await settle(cancelled())

    async def it_raises_a_cancel_that_came_even_when_the_coroutine_then_fails() -> None:
        async def teardown() -> None:
            await asyncio.sleep(0.03)
            raise ValueError("teardown failed")

        async def settled() -> BaseException | None:
            try:
                await settle(teardown())
            except BaseException as error:
                return error
            return None

        task = asyncio.create_task(settled())
        await asyncio.sleep(0.01)
        task.cancel()
        error = await task
        assert isinstance(error, asyncio.CancelledError)
        assert isinstance(error.__cause__, ValueError)
