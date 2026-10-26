import asyncio
from typing import Any

from adocker.Container import Container
from adocker.DockerException import DockerException
from adocker.utils import run_docker, settle


async def started(container: Container, since: str) -> None:
    """Return once the daemon reports that `container` started at or after `since`.

    `since` is the daemon's own timestamp, so the events stream replays a start that came
    before it subscribed. Raises DockerException if the stream ends first.
    """
    seen: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    def saw(_chunk: bytes) -> None:
        if not seen.done():
            seen.set_result(None)

    args = (
        *("events", "--since", since, "--filter", f"container={container.name}"),
        *("--filter", "event=start", "--format", "{{.Action}}"),
    )
    stream = asyncio.ensure_future(run_docker(*args, stdout=saw))
    try:
        either: set[asyncio.Future[Any]] = {seen, stream}
        await asyncio.wait(either, return_when=asyncio.FIRST_COMPLETED)
        if not seen.done():
            await stream
            raise DockerException(["docker", *args], 0, "the event stream ended first")
    finally:
        stream.cancel()
        await settle(asyncio.gather(stream, return_exceptions=True))
