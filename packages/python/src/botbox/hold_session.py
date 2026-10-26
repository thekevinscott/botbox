import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from posix_tools import tail

from adocker import Container, Image
from botbox.agents.agent import SessionAgent
from botbox.process import settle
from botbox.Session import Session
from botbox.utils.abort_writer import abort_writer
from botbox.utils.FileLines import FileLines
from botbox.write import write


@asynccontextmanager
async def hold_session(
    agent: SessionAgent,
    image: str,
    command: Sequence[str],
    *,
    scratch: Path,
    output: Path | None,
    **options: Any,
) -> AsyncIterator[tuple[Session, Container]]:
    """Start `command` on `image` attached, with `options`, and yield a session on it.

    stdout and stderr go to stdout.txt and stderr.txt in `scratch`, and in `output` too if
    given; events are read from the scratch copy. Leaving the block stops the client if it is
    still running, through any number of cancels; the container lives on for the caller to
    remove.
    """
    also = [] if output is None else [output]
    printed = scratch / "stdout.txt"
    with (
        write(*[folder / "stdout.txt" for folder in (scratch, *also)]) as out,
        write(*[folder / "stderr.txt" for folder in (scratch, *also)]) as err,
    ):
        async with tail(printed, n=None, follow=True) as followed:
            lines = FileLines(printed, followed)

            def print_line(chunk: bytes) -> None:
                out(chunk)
                lines.grew(len(chunk))

            try:
                container = await Image(image).run(
                    *command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=print_line,
                    stderr=err,
                    **options,
                )
                client = cast("asyncio.Task[int]", container.client)
                stdin = cast("asyncio.StreamWriter", container.stdin)
                try:
                    client.add_done_callback(lambda _: lines.end())
                    yield Session(agent, stdin, client, lines.readline), container
                finally:
                    try:
                        client.cancel()
                        await settle(asyncio.gather(client, return_exceptions=True))
                    finally:
                        abort_writer(stdin)
            finally:
                await lines.close()
