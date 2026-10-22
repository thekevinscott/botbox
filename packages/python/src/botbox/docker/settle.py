import asyncio
from collections.abc import Coroutine
from typing import Any


async def settle[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run `coro` to the end through any number of cancels, then raise the cancel if one came."""
    task = asyncio.ensure_future(coro)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            cancelled = True
    if cancelled:
        raise asyncio.CancelledError
    return task.result()
