"""A caller's layer that changes who the agent runs as, or wraps it in an ENTRYPOINT.

Either way the agent still reaches its proxy through the relay the agent image ships.
"""

import asyncio
from pathlib import Path

import pytest
from network_test import CONNECT, PROXY

from botbox import Botbox, ClaudeAgent, RunResult

OTHER_UID = """FROM botbox-claude:latest
USER root
RUN usermod -u 4242 user && groupmod -g 4242 user
USER user
"""

PROXY_UID = """FROM botbox-claude:latest
USER root
RUN usermod -u 100 user
USER user
"""

ENTRYPOINT = """FROM botbox-claude:latest
ENTRYPOINT ["/bin/sh", "-c", "echo wrapped >&2; exec \\"$@\\"", "--"]
"""


def layered(tmp_path: Path, text: str) -> RunResult:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(text)
    box = Botbox(ClaudeAgent(), dockerfile=dockerfile)
    return asyncio.run(box.run(f"id -u; {CONNECT} api.anthropic.com {PROXY}"))


@pytest.fixture
def other_uid(tmp_path: Path) -> RunResult:
    return layered(tmp_path, OTHER_UID)


@pytest.fixture
def proxy_uid(tmp_path: Path) -> RunResult:
    return layered(tmp_path, PROXY_UID)


@pytest.fixture
def entrypoint(tmp_path: Path) -> RunResult:
    return layered(tmp_path, ENTRYPOINT)


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
        assert entrypoint.stdout.split() == ["1000", "200"], entrypoint.stderr
