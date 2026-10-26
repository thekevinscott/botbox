"""The pi image: what a command run in it can use."""

import asyncio
import json
import shlex
from pathlib import Path
from typing import Any

import pytest

from botbox import Botbox, PiAgent, RunResult

INTEGRATION = Path(__file__).parents[1] / "integration"
SLEEPS = json.dumps({"command": "sleep 30; echo finished"})


@pytest.fixture(scope="module")
def result(output: Path) -> RunResult:
    box = Botbox(PiAgent("openrouter", api_key="unused"))
    return asyncio.run(box.run("python3 -c 'print(6 * 7)'", output=output))


@pytest.fixture(scope="module")
def timed_out(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """The bash call a fake model asked for, run by pi with the shipped extension loaded."""
    output = tmp_path_factory.mktemp("tool-timeout")
    command = "BOTBOX_TOOL_TIMEOUT=2 " + shlex.join(
        [
            "python3",
            "/fake/fake_model_test.py",
            SLEEPS,
            "-e",
            "/usr/local/lib/botbox/tool-timeout.ts",
        ]
    )
    box = Botbox(PiAgent("openrouter", api_key="unused"), timeout=25)
    run = box.run(command, mounts=[(INTEGRATION, "/fake", "ro")], output=output)
    assert asyncio.run(run).exit_code == 0, (output / "stderr.txt").read_text()
    lines = (output / "stdout.txt").read_text().splitlines()
    [end] = [json.loads(line) for line in lines if line.startswith('{"type":"tool_execution_end"')]
    return dict(end)


def describe_the_pi_image() -> None:
    def it_runs_python(result: RunResult, output: Path) -> None:
        assert (result.exit_code, (output / "stdout.txt").read_text()) == (0, "42\n")

    def it_ships_the_tool_timeout_extension(timed_out: dict[str, Any]) -> None:
        assert timed_out["result"]["content"] == [
            {"type": "text", "text": "Command timed out after 2 seconds"}
        ]
        assert timed_out["isError"] is True
