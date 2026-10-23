"""A model name carrying shell syntax reaches claude as one argument. Key via conftest."""

import asyncio
from pathlib import Path

import pytest
from conftest import API_KEY

from botbox import Botbox, ClaudeAgent, RunResult


@pytest.fixture(scope="module")
def result(
    output: Path,
) -> RunResult:
    agent = ClaudeAgent(model="nope; echo INJECTED", api_key=API_KEY)
    return asyncio.run(Botbox(agent).run(agent.command("say ok"), output=output))


@pytest.mark.usefixtures("result")
def describe_a_model_name_with_shell_syntax() -> None:
    @pytest.mark.usefixtures("result")
    def it_runs_no_second_command(
        output: Path,
    ) -> None:
        assert "INJECTED" not in (output / "stdout.txt").read_text(errors="replace").splitlines()

    @pytest.mark.usefixtures("result")
    def it_hands_claude_the_whole_name(
        output: Path,
    ) -> None:
        assert "nope; echo INJECTED" in (output / "stdout.txt").read_text(errors="replace") + (
            output / "stderr.txt"
        ).read_text(errors="replace")
