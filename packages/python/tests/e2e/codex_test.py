"""A real Codex session, signed in with the host's ChatGPT login. Billed."""

import asyncio
import json
from pathlib import Path

import pytest

from botbox import Botbox, CodexAgent, RunResult


@pytest.fixture(scope="module")
def result(
    output: Path,
) -> RunResult:
    agent = CodexAgent("gpt-5.6-luna", "low")
    return asyncio.run(Botbox(agent).run(agent.command("Reply with exactly: pong"), output=output))


def describe_a_codex_session() -> None:
    def it_exits_zero(output: Path, result: RunResult) -> None:
        assert result.exit_code == 0, (output / "stderr.txt").read_text(errors="replace")

    @pytest.mark.usefixtures("result")
    def it_completes_the_turn(
        output: Path,
    ) -> None:
        events = [
            json.loads(line)
            for line in (output / "stdout.txt").read_text(errors="replace").splitlines()
        ]
        assert events[-1]["type"] == "turn.completed"

    @pytest.mark.usefixtures("result")
    def it_answers(
        output: Path,
    ) -> None:
        assert "pong" in (output / "stdout.txt").read_text(errors="replace")

    @pytest.mark.usefixtures("result")
    def it_returns_the_transcript(
        output: Path,
    ) -> None:
        assert {
            str(p.relative_to(output / "transcripts")): p.read_text()
            for p in (output / "transcripts").rglob("*.jsonl")
            if p.is_file()
        }
        assert all(
            {
                str(p.relative_to(output / "transcripts")): p.read_text()
                for p in (output / "transcripts").rglob("*.jsonl")
                if p.is_file()
            }.values()
        )

    @pytest.mark.usefixtures("result")
    def it_reaches_chatgpt_through_the_proxy(
        output: Path,
    ) -> None:
        assert 'Established connection to host "chatgpt.com"' in (output / "proxy.log").read_text(
            errors="replace"
        )

    @pytest.mark.usefixtures("result")
    def it_reaches_for_no_refused_host(
        output: Path,
    ) -> None:
        refused = [
            line
            for line in (output / "proxy.log").read_text(errors="replace").splitlines()
            if "Proxying refused" in line
        ]
        assert refused == []
