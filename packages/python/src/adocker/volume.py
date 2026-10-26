import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from adocker.run_docker import run_docker

REMOVE_SECONDS = 30


@asynccontextmanager
async def volume(
    name: str,
    *,
    label: str,
    remove_seconds: float = REMOVE_SECONDS,
    on_error: Callable[[Exception], None] | None = None,
) -> AsyncIterator[str]:
    """Create the named volume `name` with `label`, yield its name, and remove it on exit.

    The removal runs to the end through any number of cancels, and gives up with TimeoutError
    after `remove_seconds`. A removal that fails goes to `on_error` if given. Without it, the
    failure is raised, unless the block already raised, whose error it never replaces.
    """
    await run_docker("volume", "create", "--label", label, name)
    failed = False
    try:
        yield name
    except BaseException:
        failed = True
        raise
    finally:
        try:
            await _settle(_remove_within(name, remove_seconds))
        except Exception as error:
            if on_error is not None:
                on_error(error)
            elif not failed:
                raise


async def _remove_within(name: str, seconds: float) -> None:
    try:
        async with asyncio.timeout(seconds):
            await run_docker("volume", "rm", "--force", name)
    except TimeoutError:
        raise TimeoutError(f"the daemon did not remove it within {seconds:g}s") from None


# Same as botbox.process.settle; adocker imports nothing from botbox.
async def _settle(coro: Awaitable[None]) -> None:
    task = asyncio.ensure_future(coro)
    cancelled = False
    while not task.done():
        try:
            await asyncio.wait({task})
        except asyncio.CancelledError:
            cancelled = True
    if cancelled:
        raise asyncio.CancelledError from task.exception()
    task.result()
