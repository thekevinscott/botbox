"""A real Claude Code run whose Bash call outlives `tool_timeout`, billed. Runs once."""

import asyncio
import time
from pathlib import Path

import pytest
from conftest import transcripts

from botbox import Botbox, ClaudeAgent, RunResult

# Not `sleep`: Claude Code never moves a command starting with `sleep` to the background,
# so it couldn't show that the limit kills instead of backgrounding.
PROMPT = (
    "Run this exact Bash command, with no timeout and not in the background:"
    " node -e \"setTimeout(() => console.log('finished'), 120000)\"."
    " Then reply with what the tool returned."
)


@pytest.fixture(scope="module")
def timed(output: Path) -> tuple[RunResult, float]:
    agent = ClaudeAgent(model="claude-opus-5", effort="low", tool_timeout=5)
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
        assert any("Command timed out" in text for text in transcripts(output).values())

    @pytest.mark.usefixtures("timed")
    def it_does_not_move_the_command_to_the_background(output: Path) -> None:
        assert not any("moved to the background" in text for text in transcripts(output).values())
