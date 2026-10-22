"""`AsyncBotbox.build()` against real Docker: turns, cancellation, and the loop while waiting.

Each test builds its own `async83-*` image from a Dockerfile whose slow step no cache holds,
watches the host's process table for the build's clients, and removes the image after.
"""

import asyncio
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

import pytest

from botbox import AsyncBotbox

SYNC_BUILD = """
import sys
from pathlib import Path
from botbox import Botbox

class Agent:
    image = sys.argv[1]
    dockerfile = Path(sys.argv[2])

Botbox(Agent()).build()
"""


class SlowAgent:
    """An agent image whose one step sleeps `seconds`, behind a marker no cache has seen."""

    def __init__(self, directory: Path, seconds: float) -> None:
        self.marker = uuid4().hex[:12]
        self.image = f"async83-{self.marker}:latest"
        self.dockerfile = directory / "Dockerfile"
        self.step = f"sleep {seconds}; echo {self.marker}"
        self.dockerfile.write_text(f"FROM busybox:latest\nRUN {self.step}\n")


def processes(needle: str) -> list[list[str]]:
    """The argv of every host process whose command line mentions `needle`."""
    found = []
    for cmdline in Path("/proc").glob("[0-9]*/cmdline"):
        with suppress(OSError):
            argv = cmdline.read_bytes().decode(errors="replace").split("\0")
            if any(needle in arg for arg in argv):
                found.append(argv)
    return found


def clients(agent: SlowAgent) -> int:
    """How many buildx clients are building `agent`'s image right now."""
    return sum(Path(argv[0]).name == "docker-buildx" for argv in processes(agent.image))


class Watch:
    """The most buildx clients of one image seen at once, sampled every 20ms."""

    def __init__(self, agent: SlowAgent) -> None:
        self.agent = agent
        self.most = 0

    async def __call__(self) -> None:
        while True:
            self.most = max(self.most, clients(self.agent))
            await asyncio.sleep(0.02)


async def until(condition: Callable[[], object], timeout: float = 120) -> None:
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.05)


async def sync_build(agent: SlowAgent) -> asyncio.subprocess.Process:
    """A sync `Botbox.build()` of `agent`, in a process of its own."""
    return await asyncio.create_subprocess_exec(
        sys.executable, "-c", SYNC_BUILD, agent.image, str(agent.dockerfile)
    )


@pytest.fixture
def agent(tmp_path: Path) -> Iterator[SlowAgent]:
    agent = SlowAgent(tmp_path, 3)
    yield agent
    subprocess.run(["docker", "image", "rm", "--force", agent.image], capture_output=True)


def describe_async_build() -> None:
    async def it_makes_two_concurrent_builds_of_one_tag_take_turns(agent: SlowAgent) -> None:
        watch = Watch(agent)
        watcher = asyncio.create_task(watch())
        box = AsyncBotbox(agent)
        tags = await asyncio.gather(box.build(), box.build())
        watcher.cancel()
        assert tags == [agent.image, agent.image]
        assert watch.most == 1

    async def it_takes_turns_with_a_sync_build_of_one_tag_in_another_process(
        agent: SlowAgent,
    ) -> None:
        watch = Watch(agent)
        watcher = asyncio.create_task(watch())
        other = await sync_build(agent)
        await until(lambda: clients(agent) == 1)
        assert await AsyncBotbox(agent).build() == agent.image
        assert await other.wait() == 0
        watcher.cancel()
        assert watch.most == 1

    async def it_keeps_the_loop_running_while_it_waits_for_the_lock(agent: SlowAgent) -> None:
        other = await sync_build(agent)
        await until(lambda: clients(agent) == 1)
        ticks = 0

        async def tick() -> None:
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        ticker = asyncio.create_task(tick())
        started = time.monotonic()
        await AsyncBotbox(agent).build()
        waited = time.monotonic() - started
        ticker.cancel()
        assert await other.wait() == 0
        assert waited > 1
        assert ticks > waited / 0.01 / 2

    def describe_cancelled_mid_build() -> None:
        @pytest.fixture
        def agent(tmp_path: Path) -> Iterator[SlowAgent]:
            agent = SlowAgent(tmp_path, 83.5)
            yield agent
            subprocess.run(["docker", "image", "rm", "--force", agent.image], capture_output=True)

        async def it_leaves_no_buildx_client_or_build_step_running(agent: SlowAgent) -> None:
            build = asyncio.create_task(AsyncBotbox(agent).build())
            await until(lambda: processes(agent.step) and clients(agent))
            build.cancel()
            async with asyncio.timeout(5):
                with pytest.raises(asyncio.CancelledError):
                    await build
            assert not processes(agent.image)
            await until(lambda: not processes(agent.step), timeout=5)

        async def it_stops_the_build_when_cancelled_twice(agent: SlowAgent) -> None:
            build = asyncio.create_task(AsyncBotbox(agent).build())
            await until(lambda: processes(agent.step) and clients(agent))
            build.cancel()
            await asyncio.sleep(0)
            build.cancel()
            async with asyncio.timeout(5):
                with pytest.raises(asyncio.CancelledError):
                    await build
            assert not processes(agent.image)
            await until(lambda: not processes(agent.step), timeout=5)
