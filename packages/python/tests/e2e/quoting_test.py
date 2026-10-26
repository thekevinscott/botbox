"""A model name carrying shell syntax reaches claude as one argument. Key via conftest."""

import asyncio
from pathlib import Path

import pytest
from conftest import API_KEY

from botbox import Botbox, ClaudeAgent


@pytest.fixture(scope="module")
def output(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("quoting")
    agent = ClaudeAgent(model="nope; echo INJECTED", api_key=API_KEY)
    asyncio.run(Botbox(agent).run(agent.command("say ok"), output=output))
    return output


def describe_a_model_name_with_shell_syntax() -> None:
    def it_runs_no_second_command(output: Path) -> None:
        assert "INJECTED" not in (output / "stdout.txt").read_text().splitlines()

    def it_hands_claude_the_whole_name(output: Path) -> None:
        streams = (output / "stdout.txt").read_text() + (output / "stderr.txt").read_text()
        assert "nope; echo INJECTED" in streams
