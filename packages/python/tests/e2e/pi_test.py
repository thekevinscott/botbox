"""The pi image: what a command run in it can use."""

import asyncio
from pathlib import Path

import pytest

from botbox import Botbox, PiAgent, RunResult


@pytest.fixture(scope="module")
def result(output: Path) -> RunResult:
    box = Botbox(PiAgent("openrouter", api_key="unused"))
    return asyncio.run(box.run("python3 -c 'print(6 * 7)'", output=output))


def describe_the_pi_image() -> None:
    def it_runs_python(result: RunResult, output: Path) -> None:
        assert (result.exit_code, (output / "stdout.txt").read_text()) == (0, "42\n")
