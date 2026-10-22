"""A real pi session on OpenRouter, billed. Needs OPENROUTER_API_KEY."""

import asyncio
import os

import pytest
from conftest import transcript

from botbox import Botbox, PiAgent, RunResult

# A module global, never a fixture or test argument: pytest prints arguments in tracebacks.
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY is empty")


@pytest.fixture(scope="module")
def result() -> RunResult:
    agent = PiAgent("openrouter", "openai/gpt-4o-mini", api_key=OPENROUTER_API_KEY)
    return asyncio.run(Botbox(agent).run(agent.command("Reply with exactly: pong")))


def describe_a_pi_session_on_openrouter() -> None:
    def it_exits_zero(result: RunResult) -> None:
        assert result.exit_code == 0, result.stderr

    def it_answers(result: RunResult) -> None:
        assert "pong" in result.stdout

    def it_returns_the_transcript(result: RunResult) -> None:
        assert transcript(result)
        assert all(transcript(result).values())

    def it_reaches_openrouter_through_the_proxy(result: RunResult) -> None:
        assert 'Established connection to host "openrouter.ai"' in result.proxy.read_text()

    def it_reaches_for_no_refused_host(result: RunResult) -> None:
        refused = [
            line for line in result.proxy.read_text().splitlines() if "Proxying refused" in line
        ]
        assert refused == []
