"""An agent running as another host uid, or in a caller's layer with its own ENTRYPOINT.

Either way the agent still reaches its proxy through the relay the agent image ships.
"""

import asyncio
import os
from pathlib import Path

import pytest
from network_test import CONNECT, PROXY

from botbox import Botbox, ClaudeAgent, RunResult

ENTRYPOINT = """FROM botbox-claude:latest
ENTRYPOINT ["/bin/sh", "-c", "echo wrapped >&2; exec \\"$@\\"", "--"]
"""


def connect(box: Botbox) -> RunResult:
    return asyncio.run(box.run(f"id -u; {CONNECT} api.anthropic.com {PROXY}"))


def as_uid(box: Botbox, uid: int) -> RunResult:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "getuid", lambda: uid)
        patch.setattr(os, "getgid", lambda: uid)
        return connect(box)


@pytest.fixture
def other_uid(box: Botbox) -> RunResult:
    return as_uid(box, 4242)


@pytest.fixture
def proxy_uid(box: Botbox) -> RunResult:
    return as_uid(box, 100)


@pytest.fixture
def entrypoint(tmp_path: Path) -> RunResult:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(ENTRYPOINT)
    return connect(Botbox(ClaudeAgent(), dockerfile=dockerfile))


def describe_an_agent_running_as_another_uid() -> None:
    def it_reaches_the_proxy(other_uid: RunResult) -> None:
        assert other_uid.stdout.split() == ["4242", "200"], other_uid.stderr


def describe_an_agent_running_as_the_proxys_uid() -> None:
    def it_refuses_to_start(proxy_uid: RunResult) -> None:
        assert proxy_uid.exit_code == 125
        assert "the agent runs as the proxy's uid 100" in proxy_uid.stderr
        assert proxy_uid.stdout == ""


def describe_a_layer_with_its_own_entrypoint() -> None:
    def it_runs_the_command_through_it_and_reaches_the_proxy(entrypoint: RunResult) -> None:
        assert "wrapped" in entrypoint.stderr
        assert entrypoint.stdout.split() == [str(os.getuid()), "200"], entrypoint.stderr
