"""Real Claude Code sessions in the box, billed. Module-scoped: each runs once."""

import asyncio
import json
from fnmatch import fnmatch
from pathlib import Path

import pytest

from botbox import Botbox, ClaudeAgent, RunResult


@pytest.fixture(scope="module")
def result(
    output: Path,
) -> RunResult:
    agent = ClaudeAgent(model="claude-opus-5", effort="low")
    return asyncio.run(Botbox(agent).run(agent.command("Reply with exactly: pong"), output=output))


@pytest.fixture(scope="module")
def out(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("out")


@pytest.fixture(scope="module")
def tool_result(output: Path, out: Path) -> RunResult:
    agent = ClaudeAgent(model="claude-opus-5", effort="low")
    prompt = "Write the text pong to /out/pong.txt using a tool. Do nothing else."
    box = Botbox(agent)
    return asyncio.run(
        box.run(agent.command(prompt), mounts=[(out, "/out", "rw")], workdir="/out", output=output)
    )


def describe_a_claude_session() -> None:
    def it_exits_zero(output: Path, result: RunResult) -> None:
        assert result.exit_code == 0, (output / "stderr.txt").read_text(errors="replace")

    @pytest.mark.usefixtures("result")
    def it_reports_no_error(
        output: Path,
    ) -> None:
        assert json.loads((output / "stdout.txt").read_text(errors="replace"))["is_error"] is False

    @pytest.mark.usefixtures("result")
    def it_returns_the_transcript(
        output: Path,
    ) -> None:
        jsonl = {
            k: v
            for k, v in {
                str(p.relative_to(output / "transcripts")): p.read_text()
                for p in (output / "transcripts").rglob("*.jsonl")
                if p.is_file()
            }.items()
            if fnmatch(k, "*/*.jsonl")
        }
        assert jsonl
        assert all(jsonl.values())

    @pytest.mark.usefixtures("result")
    def it_reaches_the_api_through_the_proxy(
        output: Path,
    ) -> None:
        assert 'Established connection to host "api.anthropic.com"' in (
            output / "proxy.log"
        ).read_text(errors="replace")

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


@pytest.mark.usefixtures("tool_result")
def describe_a_tool_call() -> None:
    @pytest.mark.usefixtures("tool_result")
    def it_is_not_denied(
        output: Path,
    ) -> None:
        assert (
            json.loads((output / "stdout.txt").read_text(errors="replace"))["permission_denials"]
            == []
        )

    def it_writes_into_the_rw_mount(tool_result: RunResult, out: Path) -> None:
        assert tool_result
        assert (out / "pong.txt").read_text().strip() == "pong"
