"""A model name carrying shell syntax reaches claude as one argument. Key via conftest."""

from collections.abc import Iterator

import pytest
from conftest import API_KEY, removed

from botbox import Botbox, ClaudeAgent, RunResult


@pytest.fixture(scope="module")
def result() -> Iterator[RunResult]:
    agent = ClaudeAgent(model="nope; echo INJECTED", api_key=API_KEY)
    yield from removed(Botbox(agent).run(agent.command("say ok")))


def describe_a_model_name_with_shell_syntax() -> None:
    def it_runs_no_second_command(result: RunResult) -> None:
        assert "INJECTED" not in result.stdout.splitlines()

    def it_hands_claude_the_whole_name(result: RunResult) -> None:
        assert "nope; echo INJECTED" in result.stdout + result.stderr
