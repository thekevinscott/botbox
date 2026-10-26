"""`Botbox.run()` against real Docker: cancels, timeouts, task groups and a killed owner.

Every run labels its containers and volumes `botbox.run=<token>`. Each run in a test, here
or in an owner it spawns, uses a `Marking` agent, which leaves a `run-<token>` marker in
the test's own temp dir.
A test sees only the tokens that appeared while it ran, and cleans up only those.
"""

import asyncio
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import docker_lines

from botbox import Botbox, ClaudeAgent, DockerException, RunResult, Timeout

HOSTILE = (
    "trap '' TERM INT HUP QUIT; kill -KILL -1 2>/dev/null; kill -KILL 1 2>/dev/null;"
    " while :; do sleep 1; done"
)

PRINT = "echo partial; echo err >&2; "
TRANSCRIPT = "echo '{}' > ~/.claude/projects/t.jsonl; "

# A `Marking`, for the owners this test spawns with TMPDIR set to its temp dir.
MARK = """
from botbox import ClaudeAgent

class Marking(ClaudeAgent):
    def stage_auth(self, home):
        super().stage_auth(home)
        (home.parent / f"run-{home.name.split('-')[1]}").touch()
"""

OWNER = f"""{MARK}
import asyncio, sys
from botbox import Botbox

asyncio.run(Botbox(Marking()).run({(PRINT + TRANSCRIPT + HOSTILE)!r}, output=sys.argv[2]))
"""

SESSION_OWNER = f"""{MARK}
import asyncio, sys
from botbox import Botbox

class Hostile(Marking):
    def session_command(self):
        return {("echo err >&2; " + TRANSCRIPT + HOSTILE)!r}

async def main():
    async with Botbox(Hostile()).session(output=sys.argv[2]) as live:
        await live.message("never answered")

asyncio.run(main())
"""

# A worker forked by the owner outlives it and inherits its descriptors.
FORKING_OWNER = f"""{MARK}
import asyncio, os, sys, time
from botbox import Botbox

class Hostile(Marking):
    def session_command(self):
        return {("echo err >&2; " + TRANSCRIPT + HOSTILE)!r}

async def main():
    async with Botbox(Hostile()).session(output=sys.argv[2]) as live:
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


def volumes(token: str) -> list[str]:
    return docker_lines(
        "volume", "ls", "--filter", f"label=botbox.run={token}", "--format", "{{.Name}}"
    )


class Marking(ClaudeAgent):
    """A Claude agent that leaves a `run-<token>` marker beside each home it stages.

    The home is staged in the temp dir, named `botbox-<token>-*`.
    """

    def stage_auth(self, home: Path) -> None:
        super().stage_auth(home)
        (home.parent / f"run-{home.name.split('-')[1]}").touch()


class Runs:
    """The runs this test started with a `Marking` agent, known by their markers in its temp dir."""

    def __init__(self, temp: Path) -> None:
        self.temp = temp

    @property
    def tokens(self) -> set[str]:
        return {p.name.removeprefix("run-") for p in self.temp.glob("run-*")}

    def homes(self) -> list[Path]:
        return [p for p in self.temp.iterdir() if HOME.fullmatch(p.name) and p.is_dir()]

    def leftovers(self) -> list[str]:
        return [
            *(f"container {c}" for t in self.tokens for c in containers(t)),
            *(f"volume {v}" for t in self.tokens for v in volumes(t)),
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
        for token in self.tokens:
            for name in containers(token):
                subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True)
            for name in volumes(token):
                subprocess.run(
                    ["docker", "volume", "rm", "-f", name], check=False, capture_output=True
                )


@pytest.fixture(scope="module")
def box() -> Botbox:
    box = Botbox(Marking())
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
    async def it_persists_streams_when_output_is_supplied(
        box: Botbox, runs: Runs, tmp_path: Path
    ) -> None:
        result = await box.run("echo out; echo err >&2; exit 5", output=tmp_path / "output")
        assert result == RunResult(5)
        assert (tmp_path / "output" / "stdout.txt").read_text() == "out\n"
        assert (tmp_path / "output" / "stderr.txt").read_text() == "err\n"
        assert "Starting main loop" in (tmp_path / "output" / "proxy.log").read_text()
        assert runs.leftovers() == []

    async def it_writes_transcripts_into_output_without_credentials(
        box: Botbox, runs: Runs, output: Path
    ) -> None:
        command = (
            "test -s ~/.claude/.credentials.json"
            " && mkdir ~/.claude/projects/w && echo '{}' > ~/.claude/projects/w/t.jsonl"
        )
        result = await box.run(command, output=output)
        assert result == RunResult(0)
        assert (output / "transcripts" / "w" / "t.jsonl").read_text() == "{}\n"
        assert [p.name for p in output.rglob("*credentials*")] == []
        assert runs.leftovers() == []

    async def it_returns_an_exit_of_125_from_the_container(
        box: Botbox, runs: Runs, output: Path
    ) -> None:
        assert (await box.run("exit 125", output=output)).exit_code == 125
        assert runs.leftovers() == []

    def describe_cancelling() -> None:
        @pytest.mark.parametrize("command", ["sleep 600", HOSTILE], ids=["plain", "hostile"])
        async def it_removes_the_runs_containers_and_home(
            box: Botbox, runs: Runs, command: str, output: Path
        ) -> None:
            task = asyncio.ensure_future(box.run(PRINT + command, output=output))
            await runs.started()
            await printed(output)
            assert await cancelled(task) < GRACE
            assert runs.leftovers() == []
            assert (output / "stdout.txt").read_text() == "partial\n"
            assert (output / "stderr.txt").read_text() == "err\n"

        async def it_finishes_through_a_second_cancel(
            box: Botbox, runs: Runs, output: Path
        ) -> None:
            task = asyncio.ensure_future(box.run(PRINT + "sleep 600", output=output))
            await runs.started()
            await printed(output)
            assert await cancelled(task, twice=True) < GRACE
            assert runs.leftovers() == []
            assert (output / "stdout.txt").read_text() == "partial\n"
            assert (output / "stderr.txt").read_text() == "err\n"

        async def it_removes_the_run_when_a_timeout_fires(
            box: Botbox, runs: Runs, output: Path
        ) -> None:
            started = time.monotonic()
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(8):
                    await box.run(PRINT + "sleep 600", output=output)
            assert time.monotonic() - started < 8 + GRACE
            assert len(runs.tokens) == 1
            assert runs.leftovers() == []
            assert (output / "stdout.txt").read_text() == "partial\n"
            assert (output / "stderr.txt").read_text() == "err\n"

        async def it_removes_the_run_and_keeps_what_it_left_when_its_timeout_runs_out(
            box: Botbox, runs: Runs, output: Path
        ) -> None:
            started = time.monotonic()
            with pytest.raises(Timeout) as raised:
                await box.run("echo partial; echo err >&2; sleep 600", output=output, timeout=8)
            assert time.monotonic() - started < 8 + GRACE
            assert raised.value.result == RunResult(-1)
            assert (output / "stdout.txt").read_text() == "partial\n"
            assert (output / "stderr.txt").read_text() == "err\n"
            assert "Starting main loop" in (output / "proxy.log").read_text()
            assert len(runs.tokens) == 1
            assert runs.leftovers() == []

    def describe_a_task_group() -> None:
        async def it_raises_the_failed_runs_error_and_removes_its_siblings(
            box: Botbox, runs: Runs, tmp_path: Path, output: Path
        ) -> None:
            layer = tmp_path / "Dockerfile"
            layer.write_text("FROM botbox-claude:latest\nRUN exit 3\n")
            broken = Botbox(Marking(), dockerfile=layer)

            async def fail_once_up() -> None:
                await runs.started(2)
                await printed(output / "sleeping")
                await printed(output / "hostile")
                await broken.run("true", output=output / "failed")

            with pytest.raises(ExceptionGroup) as raised:
                async with asyncio.TaskGroup() as group:
                    group.create_task(box.run(PRINT + "sleep 600", output=output / "sleeping"))
                    group.create_task(box.run(PRINT + HOSTILE, output=output / "hostile"))
                    group.create_task(fail_once_up())
            [error] = raised.value.exceptions
            assert isinstance(error, DockerException)
            assert len(runs.tokens) == 2
            assert runs.leftovers() == []
            for name in ("sleeping", "hostile"):
                assert (output / name / "stdout.txt").read_text() == "partial\n"
                assert (output / name / "stderr.txt").read_text() == "err\n"
            assert (output / "failed" / "stdout.txt").read_text() == ""
            assert (output / "failed" / "stderr.txt").read_text() == ""

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
                [sys.executable, "-c", holder, str(child), str(tmp_path / "output")],
                env=env,
                start_new_session=True,
            )
            try:
                await runs.started()
                stdout = "partial\n" if holder == OWNER else ""
                await wrote(tmp_path / "output", stdout)
                await asyncio.sleep(1)  # Let the hostile command take its shots first.
                owner.send_signal(signal.SIGKILL)
                owner.wait()
                started = time.monotonic()
                [token] = runs.tokens
                while containers(token, "status=running"):
                    assert time.monotonic() - started < GRACE, containers(token, "status=running")
                    await asyncio.sleep(0.1)
                assert {c.split("-")[1] for c in containers(token)} <= {"agent", "proxy"}
                assert sorted(volumes(token)) == [f"botbox-home-{token}", f"botbox-run-{token}"]
                listing = ("run", "--rm", "--volume", f"botbox-run-{token}:/v", "botbox-proxy")
                assert docker_lines(*listing, "ls", "-A", "/v") == []
                output = tmp_path / "output"
                assert (output / "stdout.txt").read_text() == stdout
                assert (output / "stderr.txt").read_text() == "err\n"
                assert (output / "transcripts" / "t.jsonl").read_text() == "{}\n"
                assert "Starting main loop" in (output / "proxy.log").read_text()
                if holder == FORKING_OWNER:
                    os.kill(int(child.read_text()), 0)  # Still holding whatever it inherited.
            finally:
                with suppress(ProcessLookupError):
                    os.killpg(owner.pid, signal.SIGKILL)
                owner.wait()


@pytest.fixture
def output(tmp_path: Path) -> Path:
    return tmp_path / "output"


async def printed(output: Path) -> None:
    """Wait for both streams before interrupting a live run."""
    async with asyncio.timeout(30):
        while ((output / "stdout.txt").read_text(), (output / "stderr.txt").read_text()) != (
            "partial\n",
            "err\n",
        ):
            await asyncio.sleep(0.05)


async def wrote(output: Path, stdout: str) -> None:
    """Wait for both streams and the transcript before killing the owner."""
    transcript = output / "transcripts" / "t.jsonl"
    async with asyncio.timeout(30):
        while (
            (output / "stdout.txt").read_text(),
            (output / "stderr.txt").read_text(),
            transcript.exists() and transcript.read_text(),
        ) != (stdout, "err\n", "{}\n"):
            await asyncio.sleep(0.05)
