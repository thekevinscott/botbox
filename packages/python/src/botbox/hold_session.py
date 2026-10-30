import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from adocker import Container, Image
from botbox.agents.Agent import Agent
from botbox.process import settle
from botbox.send_home import send_home
from botbox.Session import Session
from botbox.utils.abort_writer import abort_writer
from botbox.utils.LineBuffer import LineBuffer
from botbox.write import write


@asynccontextmanager
async def hold_session(  # noqa: PLR0913
    agent: Agent,
    image: str,
    command: Sequence[str],
    *,
    home: bytes,
    scratch: Path,
    output: Path | None,
    **options: Any,
) -> AsyncIterator[tuple[Session, Container]]:
    """Start `command` on `image` attached, with `options`, and yield a session on it.

    stdout and stderr go to stdout.txt and stderr.txt in `scratch`, and in `output` too if
    given; each stdout line also goes to the session as it is printed. Leaving the block stops
    the client if it is still running, through any number of cancels; the container lives on
    for the caller to remove.
    """
    also = [] if output is None else [output]
    with (
        write(*[folder / "stdout.txt" for folder in (scratch, *also)]) as out,
        write(*[folder / "stderr.txt" for folder in (scratch, *also)]) as err,
    ):
        printed: asyncio.Queue[bytes] = asyncio.Queue()
        buffer = LineBuffer()

        def print_lines(lines: list[bytes]) -> None:
            for line in lines:
                out(line)
                printed.put_nowait(line)

        def stdout(chunk: bytes) -> None:
            print_lines(buffer.add(chunk))

        def ended(_client: asyncio.Future[int]) -> None:
            print_lines(buffer.close())
            printed.put_nowait(b"")

        async def readline() -> bytes:
            line = await printed.get()
            if not line:
                printed.put_nowait(line)
            return line

        container = await Image(image).run(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=stdout,
            stderr=err,
            **options,
        )
        client = cast("asyncio.Task[int]", container.client)
        stdin = cast("asyncio.StreamWriter", container.stdin)
        client.add_done_callback(ended)
        try:
            await send_home(stdin, home)
            yield Session(agent, stdin, client, readline), container
        finally:
            try:
                client.cancel()
                await settle(asyncio.gather(client, return_exceptions=True))
            finally:
                abort_writer(stdin)
