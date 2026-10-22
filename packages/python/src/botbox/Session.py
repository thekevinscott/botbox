import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

from botbox.agents.agent import SessionAgent
from botbox.docker.abort_writer import abort_writer
from botbox.docker.Capture import Capture
from botbox.OutputLimitExceeded import OutputLimitExceeded
from botbox.RunResult import RunResult

# The longest line a session reads; a longer one ends the session.
LINE_LIMIT = 2**30
# Unread output past this pauses reading the CLI until the session reads on.
WINDOW = 2**20
# The tail of the lines that aren't events, kept for the result's stdout.
OUTPUT_LIMIT = 2**20


class Session:
    """An agent CLI held open in a locked-down container: one message in, one turn's events out.

    `stream()` sends a message and yields the turn's events as they arrive; `message()`
    collects them. One turn at a time. The CLI's output lands in the `stdout` capture, which
    holds only what hasn't been read, and in `stderr`. `stray` keeps the tail of the lines
    that weren't events. `client` is its attached `docker run`. `result` is set once the
    session's block is left.
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
        self.scanned = 0
        self.stray = bytearray()
        self.overflow = False
        self.turn = False
        self.result: RunResult | None = None
        client.add_done_callback(self.ended)

    def ended(self, _client: asyncio.Future[int]) -> None:
        """Wake a waiting turn, and drop input nothing will read so a write can't stall."""
        self.stdout.grew.set()
        abort_writer(self.stdin)

    async def stream(self, text: str) -> AsyncIterator[dict[str, Any]]:
        """Send `text` and yield the turn's events as they arrive, ending at the turn's end.

        Lines that aren't JSON objects stay in the result's stdout but aren't events. If the
        CLI exits mid-turn, the stream ends with what arrived. A turn left early is read to its
        end before the next message goes. A line over `LINE_LIMIT` kills the CLI and raises
        `OutputLimitExceeded`, as does every read after it.
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

    async def drain(self) -> None:
        """Read the CLI's output to its exit, dropping the events."""
        while await self.event() is not None:
            pass

    def output(self) -> str:
        """The tail of the lines that weren't events, once what's left unread is sorted."""
        printed = self.stdout.into
        for line in printed.splitlines(keepends=True):
            self.sort(line)
        del printed[:]
        return self.stray.decode(errors="replace")

    async def event(self) -> dict[str, Any] | None:
        """The next JSON object the CLI prints; None once it has exited without another."""
        printed, grew = self.stdout.into, self.stdout.grew
        while True:
            if self.overflow:
                raise OutputLimitExceeded(f"the agent printed a line over {LINE_LIMIT} bytes")
            grew.clear()
            end = printed.find(b"\n", self.scanned)
            if end < 0:
                self.scanned = len(printed)
                if len(printed) > LINE_LIMIT:
                    self.overflow = True
                    self.client.cancel()
                    del printed[:]
                    continue
                if not self.client.done():
                    self.stdout.resume()
                    await grew.wait()
                    continue
                if not printed:
                    return None
                end = len(printed)
            line = printed[: end + 1]
            del printed[: end + 1]
            self.scanned = 0
            if (event := self.sort(line)) is not None:
                return event

    def sort(self, line: bytearray) -> dict[str, Any] | None:
        """The event on `line`, or None with the line kept in `stray`."""
        with suppress(ValueError):
            event = json.loads(line)
            if isinstance(event, dict):
                return event
        self.stray += line
        del self.stray[: max(len(self.stray) - OUTPUT_LIMIT, 0)]
        return None
