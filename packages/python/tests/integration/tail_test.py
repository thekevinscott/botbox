import asyncio
import os
import signal
import sys
from contextlib import suppress
from pathlib import Path

import pytest


def describe_tail_owner() -> None:
    @pytest.mark.parametrize("signum", [signal.SIGKILL, signal.SIGTERM])
    async def it_stops_following_when_its_owner_dies(tmp_path: Path, signum: int) -> None:
        path = tmp_path / "stdout.txt"
        path.touch()
        script = """
import asyncio, sys
from pathlib import Path
from botbox.utils.tail import tail
spawn = asyncio.create_subprocess_exec
async def record(*args, **kwargs):
    process = await spawn(*args, **kwargs)
    print(process.pid, flush=True)
    return process
asyncio.create_subprocess_exec = record
async def main():
    async with tail(Path(sys.argv[1])):
        await asyncio.Event().wait()
asyncio.run(main())
"""
        owner = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            str(path),
            stdout=asyncio.subprocess.PIPE,
        )
        assert owner.stdout is not None
        group = 0
        try:
            async with asyncio.timeout(10):
                group = int(await owner.stdout.readline())
                owner.send_signal(signum)
                await owner.wait()
                while True:
                    check = await asyncio.create_subprocess_exec(
                        "ps",
                        "-eo",
                        "pgid=,stat=",
                        stdout=asyncio.subprocess.PIPE,
                    )
                    status, _ = await check.communicate()
                    alive = [line.split() for line in status.decode().splitlines()]
                    if not any(
                        int(pid) == group and not state.startswith("Z") for pid, state in alive
                    ):
                        break
                    await asyncio.sleep(0.02)
        finally:
            if owner.returncode is None:
                owner.kill()
                await owner.wait()
            if group:
                with suppress(ProcessLookupError):
                    os.killpg(group, signal.SIGKILL)
