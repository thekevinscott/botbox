from collections.abc import Sequence
from pathlib import Path

from python_on_whales.exceptions import DockerException

from botbox.agents.agent import Agent
from botbox.async_build_lock import async_build_lock
from botbox.build_steps import build_steps
from botbox.docker.build import build as docker_build
from botbox.docker.DockerException import DockerException as CommandFailed


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
                try:
                    await docker_build(
                        step.context, tag=step.tag, file=step.file, contexts=step.contexts
                    )
                except CommandFailed as error:
                    # The sync API's exception, until botbox's own replaces it (#86).
                    raise DockerException(
                        error.docker_command, error.return_code, stderr=error.stderr.encode()
                    ) from error
        return steps[-1].tag
