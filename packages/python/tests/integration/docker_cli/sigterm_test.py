"""SIGTERM to a process holding an `async with Botbox(...)` block, against the fake docker."""

import asyncio
import os
import signal
import sys
from pathlib import Path

import pytest
from fake_docker_test import Daemon, temp_dirs

from botbox import Botbox

HOLDER = """
import asyncio, signal, sys
from pathlib import Path
from botbox import Botbox, ClaudeAgent

home, moment = Path(sys.argv[1]), sys.argv[2]

class CopyingClaude(ClaudeAgent):
    def __init__(self, **options):
        super().__init__(**options)
        self.credential_source = None

async def main():
    if moment == "own_handler":
        task = asyncio.current_task()
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)
    try:
        async with Botbox(CopyingClaude(api_key="sk-test", host_home=home)) as box:
            await box.run("hang")
    except asyncio.CancelledError:
        sys.exit(7)

asyncio.run(main())
"""


async def hold(tmp_path: Path, temp: Path, moment: str) -> asyncio.subprocess.Process:
    """The holder, with the `box` fixture's Claude home and its temp homes going to `temp`."""
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        HOLDER,
        str(tmp_path / "claude-home"),
        moment,
        env={**os.environ, "TMPDIR": str(temp)},
    )


@pytest.fixture(autouse=True)
def plan(daemon: Daemon) -> None:
    daemon.agent("hang", mode="hang")


def describe_sigterm() -> None:
    async def it_tears_down_and_exits_143(
        box: Botbox,  # noqa: ARG001
        tmp_path: Path,
        daemon: Daemon,
        temp: Path,
    ) -> None:
        holder = await hold(tmp_path, temp, "run")
        try:
            await daemon.hanging()
            holder.send_signal(signal.SIGTERM)
            async with asyncio.timeout(20):
                assert await holder.wait() == 143
        finally:
            if holder.returncode is None:
                holder.kill()
                await holder.wait()
        assert daemon.containers == []
        assert temp_dirs(temp) == []

    async def it_leaves_a_handler_the_program_set_alone(
        box: Botbox,  # noqa: ARG001
        tmp_path: Path,
        daemon: Daemon,
        temp: Path,
    ) -> None:
        holder = await hold(tmp_path, temp, "own_handler")
        try:
            await daemon.hanging()
            holder.send_signal(signal.SIGTERM)
            async with asyncio.timeout(20):
                assert await holder.wait() == 7
        finally:
            if holder.returncode is None:
                holder.kill()
                await holder.wait()
        assert daemon.containers == []
        assert temp_dirs(temp) == []
