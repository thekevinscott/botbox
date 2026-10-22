"""A model name carrying shell syntax reaches claude as one argument. Key via conftest."""

import asyncio

import pytest
from conftest import API_KEY

from botbox import Botbox, ClaudeAgent, RunResult


@pytest.fixture(scope="module")
def result() -> RunResult:
    agent = ClaudeAgent(model="nope; echo INJECTED", api_key=API_KEY)
    return asyncio.run(Botbox(agent).run(agent.command("say ok")))


def describe_a_model_name_with_shell_syntax() -> None:
    def it_runs_no_second_command(result: RunResult) -> None:
        assert "INJECTED" not in result.stdout.splitlines()

    def it_hands_claude_the_whole_name(result: RunResult) -> None:
        assert "nope; echo INJECTED" in result.stdout + result.stderr
