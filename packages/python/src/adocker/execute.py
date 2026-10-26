import asyncio
from collections.abc import Sequence
from contextlib import AsyncExitStack, suppress
from typing import IO, Any

from posix_tools import spawn

from adocker.Pump import Pump, Sink

type Stream = int | IO[Any] | None


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
    cancelled or fails first, the client is killed and its group stopped and reaped before the
    error propagates.
    """
    async with AsyncExitStack() as stack:
        pumps: list[Pump] = []
        streams: list[Stream] = []
        for stream in (stdout, stderr):
            if callable(stream):
                pump = await stack.enter_async_context(Pump(stream))
                pumps.append(pump)
                streams.append(pump.write)
            else:
                streams.append(stream)
        async with spawn(
            "docker", *args, stdin=stdin, stdout=streams[0], stderr=streams[1]
        ) as process:
            for pump in pumps:
                pump.release()
            if started is not None:
                started.set_result(None)
            try:
                code = await process.wait()
                await asyncio.gather(*(asyncio.shield(pump.eof) for pump in pumps))
            except BaseException:
                # `docker run` forwards SIGTERM to its container and keeps waiting.
                with suppress(ProcessLookupError):
                    process.kill()
                await process.wait()
                raise
    return code
