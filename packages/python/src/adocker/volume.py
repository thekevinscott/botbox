from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from adocker.remove_volume import remove_volume
from adocker.run_docker import run_docker
from adocker.settle import settle

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
    try:
        yield name
    except BaseException:
        try:
            await settle(remove_volume(name, remove_seconds))
        except Exception as error:
            if on_error is not None:
                on_error(error)
        raise
    try:
        await settle(remove_volume(name, remove_seconds))
    except Exception as error:
        if on_error is None:
            raise
        on_error(error)
