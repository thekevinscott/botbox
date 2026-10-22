import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

from botbox.agents.agent import SessionAgent
from botbox.docker.Capture import Capture
from botbox.RunResult import RunResult


class AsyncSession:
    """`Session` for asyncio: an agent CLI held open in a locked-down container.

    `stream()` sends a message and yields the turn's events as they arrive; `message()`
    collects them. One turn at a time. The CLI's output lands in the `stdout` capture and in
    `stderr`, and `client` is its attached `docker run`. `result` is set once the session's
    block is left.
    """

    def __init__(
        self,
        agent: SessionAgent,
        stdin: asyncio.StreamWriter,
        stdout: Capture,
        stderr: bytearray,
        client: asyncio.Future[int],
    ) -> None:
        self.agent = agent
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.client = client
        self.read = 0
        self.turn = False
        self.result: RunResult | None = None
        client.add_done_callback(self.ended)

    def ended(self, _client: asyncio.Future[int]) -> None:
        """Wake a waiting turn, and drop input nothing will read so a write can't stall."""
        self.stdout.grew.set()
        self.stdin.transport.abort()

    async def stream(self, text: str) -> AsyncIterator[dict[str, Any]]:
        """Send `text` and yield the turn's events as they arrive, ending at the turn's end.

        Lines that aren't JSON objects stay in the result's stdout but aren't events. If the
        CLI exits mid-turn, the stream ends with what arrived. A turn left early is read to its
        end before the next message goes.
        """
        while self.turn and (event := await self.event()) is not None:
            self.turn = not self.agent.turn_ended(event)
        with suppress(ConnectionError):
            self.stdin.write((self.agent.encode(text) + "\n").encode())
            await self.stdin.drain()
        self.turn = True
        while self.turn and (event := await self.event()) is not None:
            self.turn = not self.agent.turn_ended(event)
            yield event

    async def message(self, text: str) -> list[dict[str, Any]]:
        """Send `text` and return the turn's events, once the agent says the turn is over."""
        return [event async for event in self.stream(text)]

    async def event(self) -> dict[str, Any] | None:
        """The next JSON object the CLI prints; None once it has exited without another."""
        printed, grew = self.stdout.into, self.stdout.grew
        while True:
            grew.clear()
            end = printed.find(b"\n", self.read)
            if end < 0:
                if self.client.done():
                    return None
                await grew.wait()
                continue
            line = bytes(printed[self.read : end])
            self.read = end + 1
            with suppress(ValueError):
                event = json.loads(line)
                if isinstance(event, dict):
                    return event
