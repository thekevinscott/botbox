"""adocker against a fake `docker` on PATH: what it is run with, and how it is stopped."""

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

from adocker import Container, DockerException, Dockerfile, Image

Install = Callable[[str], None]

RECORD = """
import json, os, sys
print(json.dumps({"argv": sys.argv[1:], "leader": os.getsid(0) == os.getpid()}))
"""

# What `Image.run` asks before it attaches: the rest of the script is the attached client.
ATTACHED = """
import sys, time
if sys.argv[1] == "create":
    sys.exit(0)
if sys.argv[1] == "container":
    print('[{"Created": "T"}]')
    sys.exit(0)
if sys.argv[1] == "events":
    print("start", flush=True)
    time.sleep(60)
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


async def cancel_twice(task: asyncio.Task[object]) -> None:
    task.cancel()
    await asyncio.sleep(0.01)
    task.cancel()
    # Not asyncio.timeout: a teardown that absorbs cancels would absorb its cancel too.
    await asyncio.wait({task}, timeout=10)
    assert task.cancelled()


def describe_docker() -> None:
    async def it_runs_docker_in_a_session_of_its_own(install: Install) -> None:
        install("import json, os; print(json.dumps([{'leader': os.getsid(0) == os.getpid()}]))")
        assert (await Container("sdk-box").inspect())["leader"] is True

    async def it_raises_what_docker_said_when_it_fails(install: Install) -> None:
        install("import sys; print('Cannot connect to the daemon', file=sys.stderr); sys.exit(1)")
        with pytest.raises(DockerException, match="Cannot connect to the daemon"):
            await Container("sdk-box").inspect()

    async def it_builds_with_buildx(install: Install, tmp_path: Path) -> None:
        out = tmp_path / "argv"
        install(f"import json, sys; open({str(out)!r}, 'w').write(json.dumps(sys.argv[1:]))")
        image = await Dockerfile(tmp_path / "D", context=tmp_path).build(
            "sdk-x:latest", contexts={"b": "/r"}
        )
        assert image.tag == "sdk-x:latest"
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

    async def it_reads_an_images_id(install: Install) -> None:
        install('print(\'[{"Id": "sha256:abc"}]\')')
        assert (await Image("sdk-x:latest").inspect())["Id"] == "sha256:abc"

    async def it_reads_the_exit_code_wait_prints(install: Install) -> None:
        install("print(3)")
        assert await Container("sdk-box").wait() == 3

    async def it_force_removes(install: Install) -> None:
        install(RECORD)
        await Container("sdk-box").remove()

    async def it_runs_an_attached_run_to_its_exit_into_its_sinks(install: Install) -> None:
        install(
            ATTACHED + "print(sys.argv[1:], sys.stdin.read()); "
            "print('said this', file=sys.stderr); sys.exit(3)"
        )
        stdout, stderr = bytearray(), bytearray()
        container = await Image("busybox").run(
            "cat",
            name="box",
            stdin=asyncio.subprocess.PIPE,
            stdout=stdout.extend,
            stderr=stderr.extend,
        )
        assert container.stdin is not None
        container.stdin.write(b"hello")
        container.stdin.close()
        assert await container.wait() == 3
        assert stdout == b"['start', '--attach', '--interactive', 'box'] hello\n"
        assert stderr == b"said this\n"

    async def it_kills_an_attached_run_that_ignores_the_terminate_when_cancelled(
        install: Install, pids: Path
    ) -> None:
        install(ATTACHED + STUBBORN)
        container = await Image("img").run(name="box", stdin=None)
        (client,) = await started(pids)
        task = asyncio.ensure_future(container.wait())
        # A cancel before the wait's first step never reaches the client.
        await asyncio.sleep(0)
        started_at = time.monotonic()
        await cancel_twice(task)
        assert await gone(client)
        assert time.monotonic() - started_at < 1

    def describe_stopping() -> None:
        async def it_reaps_a_client_that_floods_stderr_while_stopping(
            install: Install, pids: Path
        ) -> None:
            install(FLOOD)
            task = asyncio.create_task(Dockerfile("D").build("sdk-x:latest"))
            client, child = await started(pids)
            await cancel_twice(task)
            assert await gone(client)
            assert await gone(child)

        async def it_reaps_the_group_when_cancelled_before_spawn_returns(
            install: Install,
        ) -> None:
            install(PLUGIN)
            marker = f"sdk-{uuid4().hex}"
            task = asyncio.create_task(Dockerfile("D", context=marker).build("sdk-x:latest"))
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

    async def it_hands_over_complete_binary_output(install: Install) -> None:
        install(
            ATTACHED
            + "import os, sys; os.write(1, b'x' * 131072); os.write(2, b'err\\xff'); sys.exit(3)"
        )
        out, err = bytearray(), bytearray()
        container = await Image("image").run(name="box", stdout=out.extend, stderr=err.extend)
        assert await container.wait() == 3
        assert out == b"x" * 131072
        assert err == b"err\xff"

    async def it_fails_the_wait_when_a_sink_fails(install: Install) -> None:
        install(ATTACHED + "import os; os.write(1, b'out'); os.write(2, b'err')")

        def full(_chunk: bytes) -> None:
            raise OSError("disk full")

        container = await Image("image").run(name="box", stdout=full)
        with pytest.raises(OSError, match="disk full"):
            await container.wait()
