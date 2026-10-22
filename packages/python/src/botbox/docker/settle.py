import asyncio
from collections.abc import Coroutine
from typing import Any


async def settle[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run `coro` to the end through any number of cancels, then raise the cancel if one came.

    A cancel that came is raised even if `coro` failed, with the failure as its cause.
    """
    task = asyncio.ensure_future(coro)
    cancelled = False
    while not task.done():
        try:
            await asyncio.wait({task})
        except asyncio.CancelledError:
            cancelled = True
    if cancelled:
        raise asyncio.CancelledError from task.exception()
    return task.result()
