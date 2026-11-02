"""The pi image: what a command run in it can use."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from conftest import OPENROUTER_API_KEY

from botbox import Botbox, PiAgent, RunResult

PROMPT = (
    "Run this exact bash command, with no timeout: sleep 30; echo finished. "
    "Then reply with what the tool returned."
)


@pytest.fixture(scope="module")
def result(output: Path) -> RunResult:
    box = Botbox(PiAgent("openrouter", "openai/gpt-4o-mini", api_key=OPENROUTER_API_KEY))
    return asyncio.run(box.run("python3 -c 'print(6 * 7)'", output=output))


@pytest.fixture(scope="module")
def timed_out(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """The real model's bash call, run by pi with the shipped extension loaded."""
    output = tmp_path_factory.mktemp("tool-timeout")
    agent = PiAgent("openrouter", "openai/gpt-4o-mini", api_key=OPENROUTER_API_KEY, tool_timeout=2)
    box = Botbox(agent, timeout=60)
    run = box.run(agent.command(PROMPT), output=output)
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
