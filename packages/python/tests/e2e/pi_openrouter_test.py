"""A real pi session on OpenRouter, billed. Needs OPENROUTER_API_KEY."""

import asyncio
import os
from pathlib import Path

import pytest
from conftest import transcripts

from botbox import Botbox, PiAgent, RunResult

# A module global, never a fixture or test argument: pytest prints arguments in tracebacks.
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY is empty")


@pytest.fixture(scope="module")
def result(output: Path) -> RunResult:
    agent = PiAgent("openrouter", "openai/gpt-4o-mini", api_key=OPENROUTER_API_KEY)
    return asyncio.run(Botbox(agent).run(agent.command("Reply with exactly: pong"), output=output))


def describe_a_pi_session_on_openrouter() -> None:
    def it_exits_zero(result: RunResult, output: Path) -> None:
        assert result.exit_code == 0, (output / "stderr.txt").read_text()

    @pytest.mark.usefixtures("result")
    def it_answers(output: Path) -> None:
        assert "pong" in (output / "stdout.txt").read_text()

    @pytest.mark.usefixtures("result")
    def it_keeps_the_final_message_but_drops_streaming_updates(output: Path) -> None:
        stdout = (output / "stdout.txt").read_text()
        assert '{"type":"message_end"' in stdout
        assert '"type":"message_update"' not in stdout

    @pytest.mark.usefixtures("result")
    def it_writes_the_transcript(output: Path) -> None:
        transcript = transcripts(output)
        assert transcript
        assert all(transcript.values())

    @pytest.mark.usefixtures("result")
    def it_reaches_openrouter_through_the_proxy(output: Path) -> None:
        proxy = (output / "proxy.log").read_text()
        assert 'Established connection to host "openrouter.ai"' in proxy

    @pytest.mark.usefixtures("result")
    def it_reaches_for_no_refused_host(output: Path) -> None:
        proxy = (output / "proxy.log").read_text()
        assert [line for line in proxy.splitlines() if "Proxying refused" in line] == []
