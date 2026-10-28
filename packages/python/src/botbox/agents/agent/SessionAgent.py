from typing import Any, Protocol, runtime_checkable

from botbox.agents.agent.Agent import Agent


@runtime_checkable
class SessionAgent(Agent, Protocol):
    """An agent whose CLI can hold a live session: messages in on stdin, events out on stdout."""

    def session_command(self) -> str:
        """The CLI invocation that reads messages from stdin until stdin closes."""
        ...

    def encode(self, message: str) -> str:
        """`message` as one line for the CLI's stdin, without the trailing newline."""
        ...

    def turn_ended(self, event: dict[str, Any]) -> bool:
        """Whether `event`, one line of the CLI's stdout, is the last of a turn."""
        ...
