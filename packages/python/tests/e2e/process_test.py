import asyncio
import signal
import sys
from pathlib import Path

from posix_tools.process import child


def describe_child() -> None:
    async def it_escalates_and_drains_a_real_child_that_ignores_term() -> None:
        async with child(
            sys.executable,
            "-c",
            "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "print('ready', flush=True); time.sleep(60)",
            stdout=asyncio.subprocess.PIPE,
            grace=0.01,
        ) as process:
            assert process.stdout is not None
            async with asyncio.timeout(5):
                assert await process.stdout.readline() == b"ready\n"
        assert process.returncode == -signal.SIGKILL
        assert process.stdout.at_eof()

    async def it_borrows_output_files_and_preserves_the_exit_code(tmp_path: Path) -> None:
        path = tmp_path / "output"
        with path.open("wb") as output:
            async with child(
                sys.executable, "-c", "print('saved'); raise SystemExit(3)", stdout=output
            ) as process:
                assert await process.wait() == 3
            assert not output.closed
        assert path.read_bytes() == b"saved\n"
