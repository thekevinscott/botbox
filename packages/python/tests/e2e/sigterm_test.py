"""SIGTERM to a process holding an open box: nothing the box started may outlive it."""

import signal
import subprocess
import sys
import time
from collections.abc import Callable

import pytest
from conftest import leftovers

from botbox import Botbox

HOLDER = """
from botbox import Botbox, ClaudeAgent

with Botbox(ClaudeAgent()) as box:
    box.run("sleep 600")
"""


def mid_run(new: set[str]) -> bool:
    return any(n.startswith("container botbox-agent-") for n in new)


def mid_setup(new: set[str]) -> bool:
    return any(n.startswith("network botbox-jail-") for n in new)


def wait_for(condition: Callable[[], bool], timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise TimeoutError
        time.sleep(0.1)


def describe_sigterm() -> None:
    @pytest.mark.parametrize("moment", [mid_run, mid_setup])
    def it_leaves_nothing_behind(box: Botbox, moment: Callable[[set[str]], bool]) -> None:  # noqa: ARG001
        before = leftovers()
        holder = subprocess.Popen([sys.executable, "-c", HOLDER])
        try:
            wait_for(lambda: moment(leftovers() - before))
            holder.send_signal(signal.SIGTERM)
            assert holder.wait(timeout=60) == 143
        finally:
            holder.kill()
        assert leftovers() == before
