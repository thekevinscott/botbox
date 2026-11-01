"""SIGTERM to a process holding an `async with Botbox(...)` block: nothing may outlive it.

The holder wraps the step that starts the agent container. It reports the agent's name, whose
suffix is the token every container, volume and temp directory of the run is named with, then
either goes on (mid-run) or waits forever with the proxy up and the agent not yet started
(mid-setup), so the signal lands at a known point instead of a race.
"""

import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from conftest import leftovers

from botbox import Botbox

HOLDER = """
import asyncio, importlib, sys
from botbox import Botbox, ClaudeAgent

module = importlib.import_module("botbox.Botbox")

class Image(module.Image):
    async def run(self, *command, **options):
        print(options["name"], flush=True)
        if sys.argv[1] == "mid_setup":
            await asyncio.Event().wait()
        return await super().run(*command, **options)

module.Image = Image

async def main():
    async with Botbox(ClaudeAgent()) as box:
        await box.run("sleep 600")

asyncio.run(main())
"""


def wait_for(condition: Callable[[], bool], timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise TimeoutError
        time.sleep(0.1)


def left_by(token: str) -> set[str]:
    return {name for name in leftovers() if token in name}


@pytest.fixture
def tokens() -> Iterator[list[str]]:
    """The run tokens the holder reports; whatever the test leaves of those runs is removed."""
    started: list[str] = []
    yield started
    for token in started:
        for name in left_by(token):
            kind, _, rest = name.partition(" ")
            if kind == "container":
                subprocess.run(["docker", "rm", "-f", rest], check=False, capture_output=True)
            elif kind == "volume":
                subprocess.run(
                    ["docker", "volume", "rm", "-f", rest], check=False, capture_output=True
                )
            elif kind == "temp":
                shutil.rmtree(Path(tempfile.gettempdir()) / rest, ignore_errors=True)


def describe_sigterm() -> None:
    @pytest.mark.parametrize("moment", ["mid_run", "mid_setup"])
    def it_leaves_nothing_behind(
        box: Botbox,  # noqa: ARG001
        moment: str,
        tokens: list[str],
    ) -> None:
        holder = subprocess.Popen(
            [sys.executable, "-c", HOLDER, moment],
            stdout=subprocess.PIPE,
            text=True,
        )
        assert holder.stdout is not None
        try:
            agent = holder.stdout.readline().strip()
            token = agent.removeprefix("botbox-agent-")
            assert token != agent, agent
            tokens.append(token)
            if moment == "mid_run":
                wait_for(lambda: f"container {agent}" in leftovers())
            else:
                now = leftovers()
                assert f"container botbox-proxy-{token}" in now
                assert f"container {agent}" not in now
            holder.send_signal(signal.SIGTERM)
            assert holder.wait(timeout=60) == 143
        finally:
            holder.kill()
            holder.wait()
        assert not left_by(token)
