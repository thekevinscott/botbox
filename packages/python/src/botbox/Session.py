import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Any

from botbox.agents.Agent import Agent
from botbox.RunResult import RunResult
from botbox.utils.abort_writer import abort_writer


class Session:
    """An agent CLI held open in a locked-down container: one message in, one turn's events out.

    `stream()` sends a message and yields the turn's events as they arrive; `message()`
    collects them. One turn at a time. `client` is the CLI's attached `docker run`, and
    `readline` reads its stdout; once it returns b"" it is not called again. `result` is set
    once the session's block is left.
    """

    def __init__(
        self,
        agent: Agent,
        stdin: asyncio.StreamWriter,
        client: asyncio.Future[int],
        readline: Callable[[], Awaitable[bytes]],
    ) -> None:
        self.agent = agent
        self.stdin = stdin
        self.client = client
        self._readline = readline
        self.turn = False
        self.over = False
        self.result: RunResult | None = None
        client.add_done_callback(self.ended)

    def ended(self, _client: asyncio.Future[int]) -> None:
        """Drop input nothing will read so a write can't stall."""
        abort_writer(self.stdin)

    async def stream(self, text: str) -> AsyncIterator[dict[str, Any]]:
        """Send `text` and yield the turn's events as they arrive, ending at the turn's end.

        Lines the agent parses no event from stay in stdout but aren't events. If the
        CLI exits mid-turn, the stream ends with what arrived. A turn left early is read to its
        end before the next message goes.
        """
        while self.turn and (event := await self.event()) is not None:
            self.turn = not self.agent.turn_ended(event)
        self.stdin.write((self.agent.encode(text) + "\n").encode())
        # Before the drain: a cancel there still leaves the message queued to send.
        self.turn = True
        with suppress(ConnectionError):
            await self.stdin.drain()
        while self.turn and (event := await self.event()) is not None:
            self.turn = not self.agent.turn_ended(event)
            yield event

    async def message(self, text: str) -> list[dict[str, Any]]:
        """Send `text` and return the turn's events, once the agent says the turn is over."""
        return [event async for event in self.stream(text)]

    async def event(self) -> dict[str, Any] | None:
        """The next event the CLI prints; None once its stdout has ended without another."""
        while not self.over and (line := await self._readline()):
            if (event := self.agent.parse_event(line)) is not None:
                return event
        self.over = True
        return None
