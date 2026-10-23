"""A real pi session on OpenRouter, billed. Needs OPENROUTER_API_KEY."""

import asyncio
import os
from pathlib import Path

import pytest

from botbox import Botbox, PiAgent, RunResult

# A module global, never a fixture or test argument: pytest prints arguments in tracebacks.
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY is empty")


@pytest.fixture(scope="module")
def result(
    output: Path,
) -> RunResult:
    agent = PiAgent("openrouter", "openai/gpt-4o-mini", api_key=OPENROUTER_API_KEY)
    return asyncio.run(Botbox(agent).run(agent.command("Reply with exactly: pong"), output=output))


def describe_a_pi_session_on_openrouter() -> None:
    def it_exits_zero(output: Path, result: RunResult) -> None:
        assert result.exit_code == 0, (output / "stderr.txt").read_text(errors="replace")

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
    def it_reaches_openrouter_through_the_proxy(
        output: Path,
    ) -> None:
        assert 'Established connection to host "openrouter.ai"' in (
            output / "proxy/tinyproxy.log"
        ).read_text(errors="replace")

    @pytest.mark.usefixtures("result")
    def it_reaches_for_no_refused_host(
        output: Path,
    ) -> None:
        refused = [
            line
            for line in (output / "proxy/tinyproxy.log").read_text(errors="replace").splitlines()
            if "Proxying refused" in line
        ]
        assert refused == []
