import asyncio
from collections.abc import Callable
from typing import Self

from botbox.agents.Message import Message

type Wanted = Callable[[Message], bool]


class Subscription:
    """The messages `wanted` picks, from when it was opened until the CLI's stdout ends."""

    def __init__(self, wanted: Wanted, *, ended: bool) -> None:
        self.wanted = wanted
        self.queue: asyncio.Queue[Message | None] = asyncio.Queue()
        self.ended = ended

    def put(self, message: Message | None) -> None:
        self.queue.put_nowait(message)

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> Message:
        if not self.ended and (message := await self.queue.get()) is not None:
            return message
        self.ended = True
        raise StopAsyncIteration


class Channel:
    """A running CLI: its stdin, and every message it prints handed to each open subscription
    and each callback."""

    def __init__(self) -> None:
        self.stdin: asyncio.StreamWriter | None = None
        self.subscriptions: list[Subscription] = []
        self.callbacks: list[tuple[Wanted, Callable[[Message], object]]] = []
        self.ended = False

    async def send(self, line: bytes) -> None:
        if self.stdin is None:
            raise RuntimeError("the CLI has not started")
        self.stdin.write(line)
        await self.stdin.drain()

    def subscribe(self, wanted: Wanted) -> Subscription:
        subscription = Subscription(wanted, ended=self.ended)
        self.subscriptions.append(subscription)
        return subscription

    def listen(self, wanted: Wanted, callback: Callable[[Message], object]) -> None:
        self.callbacks.append((wanted, callback))

    def publish(self, message: Message) -> None:
        for subscription in self.subscriptions:
            if subscription.wanted(message):
                subscription.put(message)
        for wanted, callback in self.callbacks:
            if wanted(message):
                callback(message)

    def end(self) -> None:
        self.ended = True
        for subscription in self.subscriptions:
            subscription.put(None)
