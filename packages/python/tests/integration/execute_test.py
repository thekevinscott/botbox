"""`execute` against a real client that floods its stdout and ignores SIGTERM."""

import asyncio
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from adocker.utils import execute

NOISY = """
import os, signal
signal.signal(signal.SIGTERM, signal.SIG_IGN)
while True:
    os.write(1, b"x" * 65536)
"""


@pytest.fixture(autouse=True)
def noisy(tmp_path: Path) -> Iterator[None]:
    fake = tmp_path / "docker"
    fake.write_text(f"#!{sys.executable}\n{NOISY}")
    fake.chmod(0o755)
    with patch.dict(os.environ, {"PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"}):
        yield


def describe_a_noisy_client() -> None:
    async def it_is_reaped_when_cancelled_mid_stream() -> None:
        seen = asyncio.Event()
        task = asyncio.create_task(
            execute(["run"], stdin=None, stdout=lambda _: seen.set(), stderr=None)
        )
        await seen.wait()
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(asyncio.shield(task), 10)

    async def it_is_reaped_when_its_sink_fails() -> None:
        def full(_chunk: bytes) -> None:
            raise OSError("disk full")

        with pytest.raises(OSError, match="disk full"):
            await asyncio.wait_for(execute(["run"], stdin=None, stdout=full, stderr=None), 10)
