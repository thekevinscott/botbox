import asyncio
import signal
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import IO, Any

from ._close import _close
from .abandon import abandon
from .settle import settle


@asynccontextmanager
async def child(  # noqa: PLR0913 — explicit subprocess streams and cleanup policy
    program: str,
    *args: str,
    stdin: int | IO[Any] | None = None,
    stdout: int | IO[Any] | None = None,
    stderr: int | IO[Any] | None = None,
    signum: int = signal.SIGTERM,
    grace: float = 10,
    linger: float = 0,
    drains: Sequence[asyncio.Future[Any]] = (),
) -> AsyncIterator[asyncio.subprocess.Process]:
    """Own a process group through cancellation, draining its pipes only after the body exits.

    The body must stop reading owned pipes before exiting; cleanup takes over their readers.
    Borrow supplied descriptors. On normal exit, allow `linger` seconds for natural completion;
    otherwise stop the group immediately, escalating from `signum` to SIGKILL after `grace`.
    """
    starting = asyncio.ensure_future(
        asyncio.create_subprocess_exec(
            program, *args, stdin=stdin, stdout=stdout, stderr=stderr, start_new_session=True
        )
    )
    try:
        process = await asyncio.shield(starting)
    except asyncio.CancelledError:
        await settle(abandon(starting, signum=signum, grace=grace))
        raise
    failed = True
    try:
        yield process
        failed = False
    finally:
        await _close(process, drains, signum=signum, grace=grace, linger=0 if failed else linger)
