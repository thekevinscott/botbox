"""SIGTERM to a process holding an `async with Botbox(...)` block: nothing may outlive it.

The holder wraps the step that starts the agent container. It reports the names of what the
box started, then either goes on (mid-run) or waits forever with the proxy up and the agent
not yet started (mid-setup), so the signal lands at a known point instead of a race.
"""

import os
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
import tempfile
import asyncio, importlib, sys
from pathlib import Path
from botbox import Botbox, ClaudeAgent

module = importlib.import_module("botbox.Botbox")

docker_run = module.docker_run

async def wrapped(args, **streams):
    proxy = args[args.index("--pid") + 1].removeprefix("container:")
    scratch = Path(args[args.index("--volume") + 1].split(":")[0]).parent
    print(args[args.index("--name") + 1], proxy, scratch.name, flush=True)
    if sys.argv[1] == "mid_setup":
        await asyncio.Event().wait()
    return await docker_run(args, **streams)

module.docker_run = wrapped

async def main():
    async with Botbox(ClaudeAgent()) as box:
        await box.run("sleep 600", output=tempfile.mkdtemp())

asyncio.run(main())
"""


def wait_for(condition: Callable[[], bool], timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise TimeoutError
        time.sleep(0.1)


@pytest.fixture
def started() -> Iterator[set[str]]:
    """What the holder reports it started; whatever the test leaves of it is removed after."""
    names: set[str] = set()
    yield names
    for name in names & leftovers():
        kind, _, rest = name.partition(" ")
        if kind == "container":
            subprocess.run(["docker", "rm", "-f", rest], check=False, capture_output=True)
        elif kind == "temp":
            runs = Path(tempfile.gettempdir()) / f"botbox-{os.getuid()}"
            shutil.rmtree(runs / rest, ignore_errors=True)


def describe_sigterm() -> None:
    @pytest.mark.parametrize("moment", ["mid_run", "mid_setup"])
    def it_leaves_nothing_behind(
        box: Botbox,  # noqa: ARG001
        moment: str,
        started: set[str],
    ) -> None:
        holder = subprocess.Popen(
            [sys.executable, "-c", HOLDER, moment],
            stdout=subprocess.PIPE,
            text=True,
        )
        assert holder.stdout is not None
        try:
            agent, proxy, scratch = holder.stdout.readline().split()
            started |= {f"container {agent}", f"container {proxy}", f"temp {scratch}"}
            if moment == "mid_run":
                wait_for(lambda: f"container {agent}" in leftovers())
            else:
                now = leftovers()
                assert f"container {proxy}" in now
                assert f"container {agent}" not in now
            holder.send_signal(signal.SIGTERM)
            assert holder.wait(timeout=60) == 143
        finally:
            holder.kill()
            holder.wait()
        assert not started & leftovers()
