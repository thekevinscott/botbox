"""claude-opus-5-5, which Claude Code before 2.1.280 cannot call. Billed; key via conftest."""

import json
from collections.abc import Iterator

import pytest
from conftest import API_KEY, removed

from botbox import Botbox, ClaudeAgent, RunResult


@pytest.fixture(scope="module")
def result() -> Iterator[RunResult]:
    agent = ClaudeAgent(model="claude-opus-5-5", api_key=API_KEY)
    yield from removed(Botbox(agent).run(agent.command("say ok")))


def describe_claude_opus_5_5() -> None:
    def it_exits_zero(result: RunResult) -> None:
        assert result.exit_code == 0, result.stdout + result.stderr

    def it_reports_no_error(result: RunResult) -> None:
        assert json.loads(result.stdout)["is_error"] is False, result.stdout
