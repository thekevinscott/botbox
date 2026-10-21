"""SIGKILL to the process holding a box: no handler runs, so the containers must end themselves.

The agent here is hostile: it ignores every signal it can and tries to kill everything it can
see, the proxy included. It still dies, because it lives in the proxy's PID namespace and the
namespace ends when the proxy's init does.
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import docker_lines, leftovers

from botbox import Botbox

HOSTILE = (
    "trap '' TERM INT HUP QUIT; kill -KILL -1 2>/dev/null; kill -KILL 1 2>/dev/null;"
    " while :; do sleep 1; done"
)

RUN = f"""
from botbox import Botbox, ClaudeAgent

with Botbox(ClaudeAgent()) as box:
    box.run({HOSTILE!r})
"""

SESSION = f"""
from botbox import Botbox, ClaudeAgent

class Hostile(ClaudeAgent):
    def session_command(self):
        return {HOSTILE!r}

with Botbox(Hostile()) as box, box.session() as live:
    live.message("never answered")
"""

# A worker forked by the owner outlives it and inherits its descriptors.
FORKED = f"""
import os, sys, time
from botbox import Botbox, ClaudeAgent

class Hostile(ClaudeAgent):
    def session_command(self):
        return {HOSTILE!r}

with Botbox(Hostile()) as box, box.session() as live:
    child = os.fork()
    if child == 0:
        time.sleep(600)
        os._exit(0)
    open(sys.argv[1], "w").write(str(child))
    live.message("never answered")
"""

GRACE = 5


def running() -> set[str]:
    return set(docker_lines("ps", "--format", "{{.Names}}"))


def wait_for(condition: Callable[[], bool], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.1)
    return True


def settled(before: set[str], live_before: set[str]) -> bool:
    """Nothing new is running and the proxy container is gone, not just stopped."""
    proxies = (n for n in leftovers() - before if n.startswith("container botbox-proxy-"))
    return not (running() - live_before) and next(proxies, None) is None


def sockets(temps: set[str]) -> list[Path]:
    root = Path(tempfile.gettempdir())
    return [s for t in temps for s in (root / t / "sockets").glob("*")]


def describe_sigkill_of_the_owner() -> None:
    @pytest.mark.parametrize(
        "holder", [RUN, SESSION, FORKED], ids=["run", "session", "forked-child"]
    )
    def it_ends_every_container_within_seconds(
        box: Botbox,  # noqa: ARG001
        holder: str,
        tmp_path: Path,
    ) -> None:
        before, live_before = leftovers(), running()
        child = tmp_path / "child"
        owner = subprocess.Popen([sys.executable, "-c", holder, str(child)])
        try:
            assert wait_for(
                lambda: any(n.startswith("botbox-agent-") for n in running() - live_before), 120
            )
            time.sleep(1)  # Let the hostile command take its shots first.
            owner.send_signal(signal.SIGKILL)
            owner.wait()
            started = time.monotonic()
            assert wait_for(lambda: settled(before, live_before), GRACE), leftovers() - before
            elapsed = time.monotonic() - started
            new = leftovers() - before
            temps = {n.removeprefix("temp ") for n in new if n.startswith("temp ")}
            assert sockets(temps) == []
            assert not any(n.startswith(("network ", "container botbox-proxy-")) for n in new)
            # Until agent containers are --rm, the kept agent container stays, exited.
            assert {n for n in new if n.startswith("container ")} == {
                n for n in new if n.startswith("container botbox-agent-")
            }
            assert elapsed < GRACE
        finally:
            owner.kill()
            if child.exists():
                os.kill(int(child.read_text()), signal.SIGKILL)
            for name in leftovers() - before:
                kind, _, rest = name.partition(" ")
                if kind == "container":
                    subprocess.run(["docker", "rm", "-f", rest], check=False, capture_output=True)
                elif kind == "temp":
                    shutil.rmtree(Path(tempfile.gettempdir()) / rest, ignore_errors=True)
        assert leftovers() == before
