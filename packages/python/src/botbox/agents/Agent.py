from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from enum import StrEnum
from pathlib import Path
from typing import Literal

from botbox.agents.Channel import Channel
from botbox.agents.HomeFiles import HomeFiles
from botbox.agents.Message import Message
from botbox.credential_proxy import CredentialSource
from botbox.RunResult import RunResult

NO_SESSION = "NOT IMPLEMENTED: {name} has no session mode."


class Agent(ABC):
    """What botbox needs to know to run an agent's CLI in a container.

    Subclass it and implement `stage_auth` and `command`. An agent whose CLI can hold a live
    session, messages in on stdin and events out on stdout, also sets `MESSAGE_TYPE` and
    overrides `session_command`, `encode` and `read_message`.

    While `Botbox.session()` holds its CLI open, `send` writes to it, and `messages`, `replies`
    and `on` hear what it prints. `result` is set once
    the session's block is left.
    """

    MESSAGE_TYPE: type[StrEnum]
    """The harness's message types, in its own names; ASSISTANT is the agent's own."""
    channel: Channel | None = None
    """The running session's CLI, or None."""
    result: RunResult | None = None
    """How the last session ended, once its block is left."""

    image: str
    dockerfile: Path
    home: str
    """Home directory in the container. The image creates it, writable by any uid."""
    sessions_dir: str
    """Directory, relative to `home`, the CLI writes its `.jsonl` session transcripts under."""
    allow: tuple[str, ...]
    """Hosts the CLI needs the proxy to admit."""
    credential_source: CredentialSource | None = None
    """The host credential the proxy sends upstream, so the box never holds it, or None to have
    `stage_auth` copy the login in."""

    @abstractmethod
    def stage_auth(self, home: HomeFiles) -> None:
        """Stage the agent's login into `home`, written into the container's home at start: a
        copy of the host's, or a placeholder when the credential proxy sends the real one."""

    @abstractmethod
    def command(self, prompt: str) -> str:
        """The agent's CLI invocation for `prompt`, as a shell string for `run()`."""

    def session_command(self) -> str:
        """The CLI invocation that reads messages from stdin until stdin closes."""
        raise NotImplementedError(NO_SESSION.format(name=type(self).__name__))

    def encode(self, message: str) -> str:
        """`message` as one line for the CLI's stdin, without the trailing newline."""
        raise NotImplementedError(NO_SESSION.format(name=type(self).__name__))

    def read_message(self, line: bytes) -> Message | None:
        """The message `line`, one line of the CLI's stdout, holds; None if it holds none."""
        raise NotImplementedError(NO_SESSION.format(name=type(self).__name__))

    async def send(self, text: str) -> None:
        """Write `text` to the session's CLI as one message. Doesn't wait for a reply."""
        await self._live().send((self.encode(text) + "\n").encode())

    @property
    def messages(self) -> AsyncIterator[Message]:
        """Each message the CLI prints from now until its stdout ends."""
        return self._live().subscribe(everything)

    @property
    def replies(self) -> AsyncIterator[Message]:
        """Each of the agent's own messages with text, from now until the CLI's stdout ends."""
        return self._live().subscribe(self._is_reply)

    def on(self, kind: Literal["reply", "message"], callback: Callable[[Message], object]) -> None:
        """Call `callback` with each reply or message for the rest of the session. A callback
        that raises ends the session, and the error comes out of its block."""
        self._live().listen(self._is_reply if kind == "reply" else everything, callback)

    def _is_reply(self, message: Message) -> bool:
        return message.type == self.MESSAGE_TYPE["ASSISTANT"] and bool(message.text)

    def _live(self) -> Channel:
        if self.channel is None:
            raise RuntimeError(f"{type(self).__name__} has no session open")
        return self.channel


def everything(_message: Message) -> bool:
    return True
