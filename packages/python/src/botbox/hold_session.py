import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from adocker import Container, Image
from botbox.agents.Agent import Agent
from botbox.agents.Channel import Channel
from botbox.process import settle
from botbox.send_home import send_home
from botbox.utils.abort_writer import abort_writer
from botbox.utils.LineBuffer import LineBuffer
from botbox.write import write


@asynccontextmanager
async def hold_session(  # noqa: PLR0913
    agent: Agent,
    channel: Channel,
    image: str,
    command: Sequence[str],
    *,
    home: bytes,
    scratch: Path,
    output: Path | None,
    **options: Any,
) -> AsyncIterator[Container]:
    """Start `command` on `image` attached, with `options`, on `channel`, and yield it.

    stdout and stderr go to stdout.txt and stderr.txt in `scratch`, and in `output` too if
    given; each stdout line, as it is printed, then goes through the agent's `read_message`,
    and what that reads is published on `channel`. Leaving the block stops the client if it is
    still running, through any number of cancels; the container lives on for the caller to
    remove.
    """
    also = [] if output is None else [output]
    with (
        write(*[folder / "stdout.txt" for folder in (scratch, *also)]) as out,
        write(*[folder / "stderr.txt" for folder in (scratch, *also)]) as err,
    ):
        buffer = LineBuffer()

        def print_lines(lines: list[bytes]) -> None:
            for line in lines:
                out(line)
                if (message := agent.read_message(line)) is not None:
                    channel.publish(message)

        def stdout(chunk: bytes) -> None:
            print_lines(buffer.add(chunk))

        container = await Image(image).run(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=stdout,
            stderr=err,
            **options,
        )
        client = cast("asyncio.Task[int]", container.client)
        stdin = cast("asyncio.StreamWriter", container.stdin)

        def ended(_client: asyncio.Future[int]) -> None:
            # Drop input nothing will read so a send can't stall.
            abort_writer(stdin)
            try:
                print_lines(buffer.close())
            finally:
                channel.end()

        channel.stdin = stdin
        client.add_done_callback(ended)
        try:
            await send_home(stdin, home)
            yield container
        finally:
            try:
                client.cancel()
                await settle(asyncio.gather(client, return_exceptions=True))
            finally:
                abort_writer(stdin)
