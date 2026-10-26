"""A caller's layer that wraps the agent in an ENTRYPOINT.

The agent still reaches its proxy through the relay the agent image ships.
"""

import asyncio
import os
from pathlib import Path

import pytest
from network_test import CONNECT, PROXY

from botbox import Botbox, ClaudeAgent

ENTRYPOINT = """FROM botbox-claude:latest
ENTRYPOINT ["/bin/sh", "-c", "echo wrapped >&2; exec \\"$@\\"", "--"]
"""


@pytest.fixture
def entrypoint(tmp_path: Path) -> Path:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(ENTRYPOINT)
    box = Botbox(ClaudeAgent(api_key="unused"), dockerfile=dockerfile)
    output = tmp_path / "output"
    asyncio.run(box.run(f"id -u; {CONNECT} api.anthropic.com {PROXY}", output=output))
    return output


def describe_a_layer_with_its_own_entrypoint() -> None:
    def it_runs_the_command_through_it_and_reaches_the_proxy(entrypoint: Path) -> None:
        stderr = (entrypoint / "stderr.txt").read_text()
        assert "wrapped" in stderr
        stdout = (entrypoint / "stdout.txt").read_text()
        assert stdout.split() == [str(os.getuid()), "200"], stderr
