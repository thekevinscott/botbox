"""SIGTERM to a process holding an open box: nothing the box started may outlive it."""

import signal
import subprocess
import sys
import time
from collections.abc import Callable

from conftest import leftovers

from botbox import Botbox

HOLDER = """
from botbox import Botbox, ClaudeAgent

with Botbox(ClaudeAgent()) as box:
    box.run("sleep 600")
"""


def mid_run(new: set[str]) -> bool:
    return any(n.startswith("container ") and "botbox-proxy-" not in n for n in new)


def wait_for(condition: Callable[[], bool], timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise TimeoutError
        time.sleep(0.1)


def describe_sigterm() -> None:
    def it_leaves_nothing_behind_mid_run(box: Botbox) -> None:  # noqa: ARG001
        before = leftovers()
        holder = subprocess.Popen([sys.executable, "-c", HOLDER])
        try:
            wait_for(lambda: mid_run(leftovers() - before))
            holder.send_signal(signal.SIGTERM)
            assert holder.wait(timeout=60) == 143
        finally:
            holder.kill()
        assert leftovers() == before
