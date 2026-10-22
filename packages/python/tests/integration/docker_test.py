"""botbox.docker against a fake `docker` on PATH: what it is run with, and how it is stopped."""

import asyncio
import json
import os
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import suppress
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from botbox.docker.build import build
from botbox.docker.DockerException import DockerException
from botbox.docker.reap import reap
from botbox.docker.remove import remove
from botbox.docker.run import run
from botbox.docker.run_docker import run_docker
from botbox.docker.version import version
from botbox.docker.wait import wait

Install = Callable[[str], None]

RECORD = """
import json, os, sys
print(json.dumps({"argv": sys.argv[1:], "leader": os.getsid(0) == os.getpid()}))
"""

# Starts a child in its group, reports both pids, then floods stderr once told to stop.
FLOOD = """
import os, signal, subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
def flood(*_):
    for _ in range(64):
        os.write(2, b"x" * 65536)
    sys.exit(143)
signal.signal(signal.SIGTERM, flood)
with open(os.environ["PIDS"], "w") as f:
    f.write(f"{os.getpid()} {child.pid}")
time.sleep(60)
"""

STUBBORN = """
import os, signal, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
with open(os.environ["PIDS"], "w") as f:
    f.write(f"{os.getpid()}")
time.sleep(60)
"""

# Leaves a child that ignores SIGTERM holding its output, and exits. The child reports both
# pids once it is deaf, so no test signals it before then.
ORPHAN = """
import os, subprocess, sys
deaf = '''
import os, signal, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
with open(os.environ["PIDS"], "w") as f:
    f.write(f"{sys.argv[1]} {os.getpid()}")
time.sleep(60)
'''
subprocess.Popen([sys.executable, "-c", deaf, str(os.getpid())])
"""

# A plugin-like child in the group, marked so a test can find it however early it is cancelled.
PLUGIN = """
import subprocess, sys, time
subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", sys.argv[-1]])
time.sleep(60)
"""


@pytest.fixture(autouse=True)
def docker() -> None:
    """Overrides conftest's, which patches `subprocess.Popen` that asyncio spawns through."""


@pytest.fixture
def pids(tmp_path: Path) -> Iterator[Path]:
    path = tmp_path / "pids"
    with patch.dict(os.environ, {"PIDS": str(path)}):
        yield path


@pytest.fixture
def install(tmp_path: Path) -> Iterator[Install]:
    """Put a `docker` on PATH that runs the given Python."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    def install(body: str) -> None:
        docker = bin_dir / "docker"
        docker.write_text(f"#!{sys.executable}\n{body}")
        docker.chmod(0o755)

    with patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}):
        yield install


async def gone(pid: int) -> bool:
    """Whether `pid` is gone within a second; an orphan takes a moment for init to reap."""
    async with asyncio.timeout(1):
        while Path(f"/proc/{pid}").exists():
            await asyncio.sleep(0.01)
    return True


async def started(pids: Path) -> list[int]:
    async with asyncio.timeout(10):
        while not pids.exists() or not pids.read_text():
            await asyncio.sleep(0.01)
    return [int(pid) for pid in pids.read_text().split()]


def marked(marker: str) -> int:
    """How many processes have `marker` in their command line."""
    count = 0
    for cmdline in Path("/proc").glob("[0-9]*/cmdline"):
        with suppress(OSError):
            count += marker.encode() in cmdline.read_bytes()
    return count


def blocking_until(condition: Callable[[], bool], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.01)
    return True


async def exited(process: asyncio.subprocess.Process) -> None:
    async with asyncio.timeout(10):
        while process.returncode is None:
            await asyncio.sleep(0.01)


async def cancel_twice(task: asyncio.Task[object]) -> None:
    task.cancel()
    await asyncio.sleep(0.01)
    task.cancel()
    # Not asyncio.timeout: a teardown that absorbs cancels would absorb its cancel too.
    await asyncio.wait({task}, timeout=10)
    assert task.cancelled()


def describe_docker() -> None:
    async def it_runs_docker_in_a_session_of_its_own(install: Install) -> None:
        install(RECORD)
        assert json.loads(await run_docker("version"))["leader"] is True

    async def it_raises_what_docker_said_when_it_fails(install: Install) -> None:
        install("import sys; print('Cannot connect to the daemon', file=sys.stderr); sys.exit(1)")
        with pytest.raises(DockerException, match="Cannot connect to the daemon"):
            await version()

    async def it_builds_with_buildx(install: Install, tmp_path: Path) -> None:
        out = tmp_path / "argv"
        install(f"import json, sys; open({str(out)!r}, 'w').write(json.dumps(sys.argv[1:]))")
        await build(tmp_path, tag="sdk-x:latest", file=tmp_path / "D", contexts={"b": "/r"})
        assert json.loads(out.read_text()) == [
            "buildx",
            "build",
            "--load",
            "--progress=quiet",
            "--tag",
            "sdk-x:latest",
            "--file",
            str(tmp_path / "D"),
            "--build-context",
            "b=/r",
            str(tmp_path),
        ]

    async def it_parses_version_json(install: Install) -> None:
        install('print(\'{"Server": {"Version": "29.1"}}\')')
        assert await version() == {"Server": {"Version": "29.1"}}

    async def it_reads_the_exit_code_wait_prints(install: Install) -> None:
        install("print(3)")
        assert await wait("sdk-box") == 3

    async def it_force_removes(install: Install) -> None:
        install(RECORD)
        await remove("sdk-box")

    async def it_hands_back_an_attached_run_with_its_streams(install: Install) -> None:
        install("import sys; print(sys.argv[1:], sys.stdin.read())")
        process = await run(
            ["--interactive", "busybox", "cat"],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=None,
        )
        stdout, _ = await process.communicate(b"hello")
        assert stdout == b"['run', '--interactive', 'busybox', 'cat'] hello\n"

    def describe_stopping() -> None:
        async def it_reaps_a_client_that_floods_stderr_while_stopping(
            install: Install, pids: Path
        ) -> None:
            install(FLOOD)
            task = asyncio.create_task(run_docker("buildx", "build"))
            client, child = await started(pids)
            await cancel_twice(task)
            assert await gone(client)
            assert await gone(child)

        async def it_kills_a_client_that_ignores_the_terminate_after_the_grace(
            install: Install, pids: Path
        ) -> None:
            install(STUBBORN)
            process = await run([], stdin=None, stdout=None, stderr=None)
            (client,) = await started(pids)
            await reap(process, grace=0.2)
            assert await gone(client)

        async def it_kills_a_group_that_outlives_its_leader_while_holding_the_pipes(
            install: Install, pids: Path
        ) -> None:
            install(ORPHAN)
            process = await run(
                [], stdin=None, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            assert process.stdout is not None
            assert process.stderr is not None
            drains = [asyncio.ensure_future(s.read()) for s in (process.stdout, process.stderr)]
            _, child = await started(pids)
            await exited(process)
            reaping = asyncio.ensure_future(reap(process, *drains, grace=0.2))
            await asyncio.wait({reaping}, timeout=5)
            assert reaping.done()
            assert await gone(child)

        async def it_kills_a_group_that_outlives_its_leader_with_no_pipes(
            install: Install, pids: Path
        ) -> None:
            install(ORPHAN)
            process = await run([], stdin=None, stdout=None, stderr=None)
            _, child = await started(pids)
            await exited(process)
            await reap(process, grace=0.2)
            assert await gone(child)

        async def it_reaps_the_group_when_cancelled_before_spawn_returns(
            install: Install,
        ) -> None:
            install(PLUGIN)
            marker = f"sdk-{uuid4().hex}"
            task = asyncio.create_task(run_docker("buildx", "build", marker))
            # Blocks the loop once docker is forked, so spawn is still connecting its pipes
            # when the cancel lands and the plugin is up.
            for _ in range(10):
                await asyncio.sleep(0)
                if blocking_until(lambda: marked(marker) == 2, 1):
                    break
            assert marked(marker) == 2
            await cancel_twice(task)
            async with asyncio.timeout(2):
                while marked(marker):
                    await asyncio.sleep(0.01)
