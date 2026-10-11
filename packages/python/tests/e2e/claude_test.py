"""One real Claude Code session in the box, billed. Module-scoped: it runs once."""

import json
from fnmatch import fnmatch

import pytest

from botbox import Botbox, ClaudeAgent, RunResult


@pytest.fixture(scope="module")
def result() -> RunResult:
    agent = ClaudeAgent(model="claude-opus-5", effort="low")
    return Botbox(agent).run(agent.command("Reply with exactly: pong"))


def describe_a_claude_session() -> None:
    def it_exits_zero(result: RunResult) -> None:
        assert result.exit_code == 0, result.stderr

    def it_reports_no_error(result: RunResult) -> None:
        assert json.loads(result.stdout)["is_error"] is False

    def it_returns_the_transcript(result: RunResult) -> None:
        jsonl = {
            k: v for k, v in result.transcript.items() if fnmatch(k, ".claude/projects/*/*.jsonl")
        }
        assert jsonl
        assert all(jsonl.values())

    def it_reaches_the_api_through_the_proxy(result: RunResult) -> None:
        assert 'Established connection to host "api.anthropic.com"' in result.proxy
