from collections.abc import Sequence
from pathlib import Path

from botbox.agents.agent import Agent
from botbox.async_build_lock import async_build_lock
from botbox.build_steps import build_steps
from botbox.buildx import buildx


class AsyncBotbox:
    """`Botbox` for asyncio: an agent, an optional image layer on top of it, and extra hosts."""

    def __init__(
        self,
        agent: Agent,
        *,
        dockerfile: str | Path | None = None,
        allow: Sequence[str] = (),
    ) -> None:
        self.agent = agent
        self.dockerfile = None if dockerfile is None else Path(dockerfile).resolve()
        if isinstance(allow, str):
            raise TypeError(f"allow takes a sequence of hosts: pass allow=({allow!r},)")
        self.allow = tuple(allow)

    async def build(self) -> str:
        """Build the agent's image, then `dockerfile` on top, and return the final tag.

        Built on every call; Docker's layer cache keeps an unchanged build fast. Concurrent
        builds of one tag, sync or async, from any process, take turns without blocking the
        loop. Cancelling stops the build in progress.
        """
        steps = build_steps(self.agent, self.dockerfile)
        for step in steps:
            async with async_build_lock(step.tag):
                await buildx(step.context, tag=step.tag, file=step.file, contexts=step.contexts)
        return steps[-1].tag
