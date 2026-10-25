import asyncio
import signal
import sys
from pathlib import Path

import pytest

from posix_tools.process import child


def describe_child() -> None:
    async def it_survives_body_and_cleanup_cancellation(tmp_path: Path) -> None:
        stopping = tmp_path / "stopping"
        ready = asyncio.Event()
        processes: list[asyncio.subprocess.Process] = []

        async def run() -> None:
            async with child(
                sys.executable,
                "-c",
                "import signal, time, pathlib, sys; "
                "signal.signal(signal.SIGTERM, lambda *_: pathlib.Path(sys.argv[1]).touch()); "
                "print('ready', flush=True); time.sleep(60)",
                str(stopping),
                stdout=asyncio.subprocess.PIPE,
                grace=1,
            ) as process:
                processes.append(process)
                assert process.stdout is not None
                assert await process.stdout.readline() == b"ready\n"
                ready.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(run())
        try:
            async with asyncio.timeout(5):
                await ready.wait()
                task.cancel()
                while not stopping.exists():
                    await asyncio.sleep(0.01)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert processes[0].returncode == -signal.SIGKILL
            assert processes[0].stdout is not None and processes[0].stdout.at_eof()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def it_closes_stdin_and_borrows_output_so_cat_exits_normally(tmp_path: Path) -> None:
        path = tmp_path / "output"
        with path.open("wb") as output:
            async with child(
                "cat", stdin=asyncio.subprocess.PIPE, stdout=output, linger=2
            ) as process:
                assert process.stdin is not None
                process.stdin.write(b"saved\n")
            assert process.returncode == 0
            assert not output.closed
        assert path.read_bytes() == b"saved\n"
