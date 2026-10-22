"""`Botbox.run()` against real Docker: cancels, timeouts, task groups and a killed owner.

Every run labels its containers `botbox.run=<token>` and names its temp home after the token.
A test sees only the tokens that appeared while it ran, and cleans up only those.
"""

import asyncio
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import docker_lines

from botbox import Botbox, ClaudeAgent, DockerException

HOSTILE = (
    "trap '' TERM INT HUP QUIT; kill -KILL -1 2>/dev/null; kill -KILL 1 2>/dev/null;"
    " while :; do sleep 1; done"
)

OWNER = f"""
import asyncio
from botbox import Botbox, ClaudeAgent

asyncio.run(Botbox(ClaudeAgent()).run({HOSTILE!r}))
"""

SESSION_OWNER = f"""
import asyncio
from botbox import Botbox, ClaudeAgent

class Hostile(ClaudeAgent):
    def session_command(self):
        return {HOSTILE!r}

async def main():
    async with Botbox(Hostile()).session() as live:
        await live.message("never answered")

asyncio.run(main())
"""

# A worker forked by the owner outlives it and inherits its descriptors.
FORKING_OWNER = f"""
import asyncio, os, sys, time
from botbox import Botbox, ClaudeAgent

class Hostile(ClaudeAgent):
    def session_command(self):
        return {HOSTILE!r}

async def main():
    async with Botbox(Hostile()).session() as live:
        child = os.fork()
        if child == 0:
            time.sleep(600)
            os._exit(0)
        open(sys.argv[1], "w").write(str(child))
        await live.message("never answered")

asyncio.run(main())
"""

GRACE = 5
HOME = re.compile(r"botbox-[0-9a-f]{12}-.+")


def containers(token: str, *filters: str) -> list[str]:
    flags = [f for name in filters for f in ("--filter", name)]
    return docker_lines(
        "ps", "-a", "--filter", f"label=botbox.run={token}", *flags, "--format", "{{.Names}}"
    )


class Runs:
    """The runs this test started, known by the temp homes they make in its own temp dir.

    A thread watches the dir, so a run's token is seen even if it is gone by the next look.
    """

    def __init__(self, temp: Path) -> None:
        self.temp = temp
        self.tokens: set[str] = set()
        self.done = threading.Event()
        self.watcher = threading.Thread(target=self.watch)
        self.watcher.start()

    def watch(self) -> None:
        while not self.done.wait(0.02):
            self.tokens |= {p.name.split("-")[1] for p in self.homes()}

    def homes(self) -> list[Path]:
        return [p for p in self.temp.iterdir() if HOME.fullmatch(p.name) and p.is_dir()]

    def leftovers(self) -> list[str]:
        return [
            *(f"container {c}" for t in self.tokens for c in containers(t)),
            *(f"temp {h.name}" for h in self.homes()),
        ]

    def running_agents(self) -> list[str]:
        return [
            c
            for t in set(self.tokens)
            for c in containers(t, "status=running")
            if c.startswith("botbox-agent-")
        ]

    async def started(self, count: int = 1) -> None:
        """Wait until `count` of this test's agents are running."""
        async with asyncio.timeout(120):
            while len(self.running_agents()) < count:
                await asyncio.sleep(0.1)

    def clean(self) -> None:
        self.done.set()
        self.watcher.join()
        for token in self.tokens:
            for name in containers(token):
                subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)


@pytest.fixture(scope="module")
def box() -> Botbox:
    box = Botbox(ClaudeAgent())
    asyncio.run(box.build())
    return box


@pytest.fixture
def temp(tmp_path: Path) -> Iterator[Path]:
    """This test's own temp dir, so its runs' homes are told apart from anyone else's."""
    directory = tmp_path / "tmp"
    directory.mkdir()
    with patch.object(tempfile, "tempdir", str(directory)):
        yield directory


@pytest.fixture
def runs(temp: Path) -> Iterator[Runs]:
    runs = Runs(temp)
    yield runs
    runs.clean()


async def cancelled(task: asyncio.Task[object], *, twice: bool = False) -> float:
    """Cancel `task`, and again shortly after if `twice`; how long it took to end."""
    started = time.monotonic()
    task.cancel()
    if twice:
        await asyncio.sleep(0.2)
        task.cancel()
    await asyncio.wait({task}, timeout=30)
    assert task.cancelled()
    return time.monotonic() - started


def describe_run() -> None:
    async def it_returns_what_the_command_left(box: Botbox, runs: Runs) -> None:
        result = await box.run("echo out; echo err >&2; exit 5")
        assert (result.stdout, result.stderr, result.exit_code) == ("out\n", "err\n", 5)
        assert result.image == "botbox-claude:latest"
        assert result.transcript == {}
        assert "Starting main loop" in result.proxy
        assert len(runs.tokens) == 1
        assert runs.leftovers() == []

    async def it_returns_an_exit_of_125_from_the_container(box: Botbox, runs: Runs) -> None:
        assert (await box.run("exit 125")).exit_code == 125
        assert runs.leftovers() == []

    def describe_cancelling() -> None:
        @pytest.mark.parametrize("command", ["sleep 600", HOSTILE], ids=["plain", "hostile"])
        async def it_removes_the_runs_containers_and_home(
            box: Botbox, runs: Runs, command: str
        ) -> None:
            task = asyncio.ensure_future(box.run(command))
            await runs.started()
            assert await cancelled(task) < GRACE
            assert runs.leftovers() == []

        async def it_finishes_through_a_second_cancel(box: Botbox, runs: Runs) -> None:
            task = asyncio.ensure_future(box.run("sleep 600"))
            await runs.started()
            assert await cancelled(task, twice=True) < GRACE
            assert runs.leftovers() == []

        async def it_removes_the_run_when_a_timeout_fires(box: Botbox, runs: Runs) -> None:
            started = time.monotonic()
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(8):
                    await box.run("sleep 600")
            assert time.monotonic() - started < 8 + GRACE
            assert len(runs.tokens) == 1
            assert runs.leftovers() == []

    def describe_a_task_group() -> None:
        async def it_raises_the_failed_runs_error_and_removes_its_siblings(
            box: Botbox, runs: Runs, tmp_path: Path
        ) -> None:
            layer = tmp_path / "Dockerfile"
            layer.write_text("FROM botbox-claude:latest\nRUN exit 3\n")
            broken = Botbox(ClaudeAgent(), dockerfile=layer)

            async def fail_once_up() -> None:
                await runs.started(2)
                await broken.run("true")

            with pytest.raises(ExceptionGroup) as raised:
                async with asyncio.TaskGroup() as group:
                    group.create_task(box.run("sleep 600"))
                    group.create_task(box.run(HOSTILE))
                    group.create_task(fail_once_up())
            [error] = raised.value.exceptions
            assert isinstance(error, DockerException)
            assert len(runs.tokens) == 2
            assert runs.leftovers() == []

    def describe_sigkill_of_the_owner() -> None:
        @pytest.mark.parametrize(
            "holder",
            [OWNER, SESSION_OWNER, FORKING_OWNER],
            ids=["run", "session", "forked-child"],
        )
        async def it_leaves_nothing_running_within_seconds(
            runs: Runs, temp: Path, tmp_path: Path, holder: str
        ) -> None:
            env = {**os.environ, "TMPDIR": str(temp)}
            child = tmp_path / "child"
            # Its own process group, so a forked child dies with it even before its pid is known.
            owner = subprocess.Popen(
                [sys.executable, "-c", holder, str(child)], env=env, start_new_session=True
            )
            try:
                await runs.started()
                await asyncio.sleep(1)  # Let the hostile command take its shots first.
                owner.send_signal(signal.SIGKILL)
                owner.wait()
                started = time.monotonic()
                [token] = runs.tokens
                while containers(token, "status=running"):
                    assert time.monotonic() - started < GRACE, containers(token, "status=running")
                    await asyncio.sleep(0.1)
                # Stopped and labelled, for a sweep to remove.
                assert {c.split("-")[1] for c in containers(token)} <= {"agent", "proxy"}
                assert [s for h in runs.homes() for s in (h / "sockets").glob("*")] == []
                if holder == FORKING_OWNER:
                    os.kill(int(child.read_text()), 0)  # Still holding whatever it inherited.
            finally:
                with suppress(ProcessLookupError):
                    os.killpg(owner.pid, signal.SIGKILL)
                owner.wait()
