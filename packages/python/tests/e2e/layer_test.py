"""A caller's layer that wraps the agent in an ENTRYPOINT.

The agent still reaches its proxy through the relay the agent image ships.
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


@pytest.fixture
def entrypoint(output: Path, tmp_path: Path) -> RunResult:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(ENTRYPOINT)
    box = Botbox(ClaudeAgent(), dockerfile=dockerfile)
    return asyncio.run(box.run(f"id -u; {CONNECT} api.anthropic.com {PROXY}", output=output))


def describe_a_layer_with_its_own_entrypoint() -> None:
    @pytest.mark.usefixtures("entrypoint")
    def it_runs_the_command_through_it_and_reaches_the_proxy(
        output: Path,
    ) -> None:
        assert "wrapped" in (output / "stderr.txt").read_text(errors="replace")
        assert (output / "stdout.txt").read_text(errors="replace").split() == [
            str(os.getuid()),
            "200",
        ], (output / "stderr.txt").read_text(errors="replace")
