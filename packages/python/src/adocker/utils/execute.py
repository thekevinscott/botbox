import asyncio
from collections.abc import Callable, Sequence
from contextlib import suppress
from typing import IO, Any

from posix_tools import spawn

type Stream = int | IO[Any] | None
type Sink = Callable[[bytes], object]

CHUNK_BYTES = 65536


async def execute(
    args: Sequence[str],
    *,
    stdin: Stream,
    stdout: Sink | Stream,
    stderr: Sink | Stream,
    started: asyncio.Future[None] | None = None,
) -> int:
    """Run `docker` and return its exit code once its output is in.

    A callable stdout or stderr is a sink: the output is piped to it chunk by chunk. Anything
    else passes to the client as is. `started` resolves once the client is spawned. If this is
    cancelled or fails first, a sink raising included, the client is killed and reaped before
    the error propagates.
    """

    async def drain(reader: asyncio.StreamReader, sink: Sink) -> None:
        while chunk := await reader.read(CHUNK_BYTES):
            sink(chunk)

    sinks = [stream if callable(stream) else None for stream in (stdout, stderr)]
    streams = [asyncio.subprocess.PIPE if callable(s) else s for s in (stdout, stderr)]
    async with spawn("docker", *args, stdin=stdin, stdout=streams[0], stderr=streams[1]) as process:
        if started is not None:
            started.set_result(None)
        drains = [
            asyncio.ensure_future(drain(reader, sink))
            for reader, sink in zip((process.stdout, process.stderr), sinks, strict=True)
            if reader is not None and sink is not None
        ]
        try:
            exited = asyncio.ensure_future(process.wait())
            await asyncio.gather(exited, *drains)
        except BaseException:
            for task in drains:
                task.cancel()
            # `docker run` forwards SIGTERM to its container and keeps waiting.
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()
            raise
    return exited.result()
