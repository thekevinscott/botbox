"""`Botbox.build()` against real Docker: concurrent builds of one tag, and cancellation.

Each test builds its own `async83-*` image from a Dockerfile whose slow step no cache holds,
watches the host's process table for the build's clients, and removes the image after.
The concurrent builds at the end build the real Claude image, as parallel runs do.
"""

import asyncio
import subprocess
import sys
from collections.abc import Callable, Iterator
from concurrent.futures import ProcessPoolExecutor
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

import pytest

from botbox import Botbox, ClaudeAgent, DockerException

OTHER_BUILD = """
import asyncio, sys
from pathlib import Path
from botbox import Botbox, ClaudeAgent, DockerException

class Other(ClaudeAgent):
    image = sys.argv[1]
    dockerfile = Path(sys.argv[2])

asyncio.run(Botbox(Other()).build())
"""
PROCESSES = 4


class SlowAgent(ClaudeAgent):
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


async def until(condition: Callable[[], object], timeout: float = 120) -> None:
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.05)


async def other_build(agent: SlowAgent) -> asyncio.subprocess.Process:
    """A `Botbox.build()` of `agent`, in a process of its own."""
    return await asyncio.create_subprocess_exec(
        sys.executable, "-c", OTHER_BUILD, agent.image, str(agent.dockerfile)
    )


def build(box: Botbox) -> str:
    """The tag, or the error's stderr."""
    try:
        return asyncio.run(box.build())
    except DockerException as error:
        return error.stderr.strip()


def build_concurrently(box: Botbox) -> list[str]:
    with ProcessPoolExecutor(PROCESSES) as pool:
        return list(pool.map(build, [box] * PROCESSES))


@pytest.fixture
def agent(tmp_path: Path) -> Iterator[SlowAgent]:
    agent = SlowAgent(tmp_path, 3)
    yield agent
    subprocess.run(["docker", "image", "rm", "--force", agent.image], capture_output=True)


def describe_build() -> None:
    async def it_builds_one_tag_twice_at_once(agent: SlowAgent) -> None:
        box = Botbox(agent)
        tags = await asyncio.gather(box.build(), box.build())
        assert list(tags) == [agent.image, agent.image]

    async def it_builds_one_tag_while_another_process_builds_it(agent: SlowAgent) -> None:
        other = await other_build(agent)
        await until(lambda: clients(agent) == 1)
        assert await Botbox(agent).build() == agent.image
        assert await other.wait() == 0

    def describe_cancelled_mid_build() -> None:
        @pytest.fixture
        def agent(tmp_path: Path) -> Iterator[SlowAgent]:
            agent = SlowAgent(tmp_path, 83.5)
            yield agent
            subprocess.run(["docker", "image", "rm", "--force", agent.image], capture_output=True)

        async def it_leaves_no_buildx_client_or_build_step_running(agent: SlowAgent) -> None:
            build = asyncio.create_task(Botbox(agent).build())
            await until(lambda: processes(agent.step) and clients(agent))
            build.cancel()
            async with asyncio.timeout(5):
                with pytest.raises(asyncio.CancelledError):
                    await build
            await until(lambda: not processes(agent.image), timeout=5)
            await until(lambda: not processes(agent.step), timeout=5)

        async def it_stops_the_build_when_cancelled_twice(agent: SlowAgent) -> None:
            build = asyncio.create_task(Botbox(agent).build())
            await until(lambda: processes(agent.step) and clients(agent))
            build.cancel()
            await asyncio.sleep(0)
            build.cancel()
            async with asyncio.timeout(5):
                with pytest.raises(asyncio.CancelledError):
                    await build
            await until(lambda: not processes(agent.image), timeout=5)
            await until(lambda: not processes(agent.step), timeout=5)


def describe_concurrent_builds_in_separate_processes() -> None:
    @pytest.mark.usefixtures("box")
    def it_returns_the_agents_tag_to_every_caller() -> None:
        assert build_concurrently(Botbox(ClaudeAgent())) == ["botbox-claude:latest"] * PROCESSES

    @pytest.mark.usefixtures("box")
    def it_returns_the_layers_tag_to_every_caller(tmp_path: Path) -> None:
        layer = tmp_path / "Dockerfile"
        layer.write_text("FROM botbox-claude:latest\nRUN echo layer > /tmp/layer\n")
        box = Botbox(ClaudeAgent(), dockerfile=layer)
        assert build_concurrently(box) == [asyncio.run(box.build())] * PROCESSES
