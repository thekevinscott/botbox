"""A real pi run on OpenRouter whose bash call outlives `tool_timeout`, billed."""

import asyncio
import os
import time
from pathlib import Path

import pytest

from botbox import Botbox, PiAgent, RunResult

# A module global, never a fixture or test argument: pytest prints arguments in tracebacks.
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY is empty")

PROMPT = (
    "Run this exact bash command, with no timeout: sleep 120 && echo finished."
    " Then reply with what the tool returned."
)


@pytest.fixture(scope="module")
def timed(output: Path) -> tuple[RunResult, float]:
    agent = PiAgent("openrouter", "openai/gpt-4o-mini", api_key=OPENROUTER_API_KEY, tool_timeout=5)
    start = time.monotonic()
    result = asyncio.run(Botbox(agent).run(agent.command(PROMPT), output=output))
    return result, time.monotonic() - start


def describe_a_bash_call_past_the_tool_timeout() -> None:
    def it_exits_zero(timed: tuple[RunResult, float], output: Path) -> None:
        assert timed[0].exit_code == 0, (output / "stderr.txt").read_text()

    def it_does_not_wait_for_the_command(timed: tuple[RunResult, float]) -> None:
        assert timed[1] < 120

    @pytest.mark.usefixtures("timed")
    def it_tells_the_model_the_command_timed_out(output: Path) -> None:
        assert "Command timed out after 5 seconds" in (output / "stdout.txt").read_text()
