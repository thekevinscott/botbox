"""`reap()` against real locks, held by this process or by an owner that dies."""

import asyncio
import os
import signal
import sys
from pathlib import Path

from fake_docker_test import runs

from botbox import reap
from botbox.Claim import Claim

OWNER = """
import os, sys, time
from botbox.Claim import Claim

claim = Claim(sys.argv[1])
if sys.argv[2] == "fork" and os.fork() == 0:
    time.sleep(600)
    os._exit(0)
open(sys.argv[3], "w").close()
time.sleep(600)
"""


async def owner(temp: Path, token: str, mode: str) -> asyncio.subprocess.Process:
    """An owner that claims `token`, maybe forks a child that outlives it, and waits to die."""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        OWNER,
        token,
        mode,
        str(temp / "held"),
        env={**os.environ, "TMPDIR": str(temp)},
        start_new_session=True,
    )
    async with asyncio.timeout(10):
        while not (temp / "held").exists():
            await asyncio.sleep(0.01)
    return process


def describe_reap() -> None:
    async def it_leaves_a_run_this_process_holds_alone() -> None:
        claim = Claim("0123456789ab")
        try:
            assert await reap() == []
            assert claim.path.exists()
        finally:
            claim.cleanup()

    async def it_reaps_a_run_whose_owner_was_killed(temp: Path) -> None:
        process = await owner(temp, "0123456789ab", "plain")
        assert await reap() == []
        process.kill()
        await process.wait()
        assert await reap() == ["0123456789ab"]
        assert list(runs(temp).iterdir()) == []

    async def it_is_not_kept_alive_by_a_child_the_owner_forked(temp: Path) -> None:
        process = await owner(temp, "0123456789ab", "fork")
        try:
            process.kill()
            await process.wait()
            assert await reap() == ["0123456789ab"]
        finally:
            os.killpg(process.pid, signal.SIGKILL)
