"""claude-opus-5-5, which Claude Code before 2.1.280 cannot call. Billed; key via conftest."""

import asyncio
import json
from pathlib import Path

import pytest
from conftest import API_KEY

from botbox import Botbox, ClaudeAgent, RunResult


@pytest.fixture(scope="module")
def result(
    output: Path,
) -> RunResult:
    agent = ClaudeAgent(model="claude-opus-5-5", api_key=API_KEY)
    return asyncio.run(Botbox(agent).run(agent.command("say ok"), output=output))


def describe_claude_opus_5_5() -> None:
    def it_exits_zero(output: Path, result: RunResult) -> None:
        assert result.exit_code == 0, (output / "stdout.txt").read_text(errors="replace") + (
            output / "stderr.txt"
        ).read_text(errors="replace")

    @pytest.mark.usefixtures("result")
    def it_reports_no_error(
        output: Path,
    ) -> None:
        assert (
            json.loads((output / "stdout.txt").read_text(errors="replace"))["is_error"] is False
        ), (output / "stdout.txt").read_text(errors="replace")
