"""A real Codex session, signed in with the host's ChatGPT login. Billed."""

import asyncio
import json
from pathlib import Path

import pytest
from conftest import transcripts

from botbox import Botbox, CodexAgent, RunResult


@pytest.fixture(scope="module")
def result(output: Path) -> RunResult:
    agent = CodexAgent("gpt-5.6-luna", "low")
    return asyncio.run(Botbox(agent).run(agent.command("Reply with exactly: pong"), output=output))


def describe_a_codex_session() -> None:
    def it_exits_zero(result: RunResult, output: Path) -> None:
        assert result.exit_code == 0, (output / "stderr.txt").read_text()

    @pytest.mark.usefixtures("result")
    def it_completes_the_turn(output: Path) -> None:
        events = [json.loads(line) for line in (output / "stdout.txt").read_text().splitlines()]
        assert events[-1]["type"] == "turn.completed"

    @pytest.mark.usefixtures("result")
    def it_answers(output: Path) -> None:
        assert "pong" in (output / "stdout.txt").read_text()

    @pytest.mark.usefixtures("result")
    def it_writes_the_transcript(output: Path) -> None:
        transcript = transcripts(output)
        assert transcript
        assert all(transcript.values())

    @pytest.mark.usefixtures("result")
    def it_reaches_chatgpt_through_the_proxy(output: Path) -> None:
        proxy = (output / "proxy.log").read_text()
        assert 'Established connection to host "chatgpt.com"' in proxy

    @pytest.mark.usefixtures("result")
    def it_reaches_for_no_refused_host(output: Path) -> None:
        proxy = (output / "proxy.log").read_text()
        assert [line for line in proxy.splitlines() if "Proxying refused" in line] == []
