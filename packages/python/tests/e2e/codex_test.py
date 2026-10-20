"""A real Codex session, signed in with the host's ChatGPT login. Billed."""

import json
from collections.abc import Iterator

import pytest
from conftest import removed

from botbox import Botbox, CodexAgent, RunResult


@pytest.fixture(scope="module")
def result() -> Iterator[RunResult]:
    agent = CodexAgent("gpt-5.6-luna", "low")
    yield from removed(Botbox(agent).run(agent.command("Reply with exactly: pong")))


def describe_a_codex_session() -> None:
    def it_exits_zero(result: RunResult) -> None:
        assert result.exit_code == 0, result.stderr

    def it_completes_the_turn(result: RunResult) -> None:
        events = [json.loads(line) for line in result.stdout.splitlines()]
        assert events[-1]["type"] == "turn.completed"

    def it_answers(result: RunResult) -> None:
        assert "pong" in result.stdout

    def it_returns_the_transcript(result: RunResult) -> None:
        assert result.transcript
        assert all(result.transcript.values())

    def it_reaches_chatgpt_through_the_proxy(result: RunResult) -> None:
        assert 'Established connection to host "chatgpt.com"' in result.proxy

    def it_reaches_for_no_refused_host(result: RunResult) -> None:
        refused = [line for line in result.proxy.splitlines() if "Proxying refused" in line]
        assert refused == []
