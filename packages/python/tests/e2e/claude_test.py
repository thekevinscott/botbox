"""Real Claude Code sessions in the box, billed. Module-scoped: each runs once."""

import asyncio
import json
import re
from fnmatch import fnmatch
from pathlib import Path

import pytest
from conftest import refused, transcripts

from botbox import Botbox, ClaudeAgent, RunResult


@pytest.fixture(scope="module")
def result(output: Path) -> RunResult:
    agent = ClaudeAgent(model="claude-opus-5", effort="low")
    return asyncio.run(Botbox(agent).run(agent.command("Reply with exactly: pong"), output=output))


@pytest.fixture(scope="module")
def out(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("out")


@pytest.fixture(scope="module")
def tool_output(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("tool_output")


@pytest.fixture(scope="module")
def tool_result(out: Path, tool_output: Path) -> RunResult:
    agent = ClaudeAgent(model="claude-opus-5", effort="low")
    prompt = "Write the text pong to /out/pong.txt using a tool. Do nothing else."
    box = Botbox(agent)
    return asyncio.run(
        box.run(
            agent.command(prompt), mounts=[(out, "/out", "rw")], workdir="/out", output=tool_output
        )
    )


def describe_a_claude_session() -> None:
    def it_exits_zero(result: RunResult, output: Path) -> None:
        assert result.exit_code == 0, (output / "stderr.txt").read_text()

    @pytest.mark.usefixtures("result")
    def it_reports_no_error(output: Path) -> None:
        assert json.loads((output / "stdout.txt").read_text())["is_error"] is False

    @pytest.mark.usefixtures("result")
    def it_writes_the_transcript(output: Path) -> None:
        jsonl = {k: v for k, v in transcripts(output).items() if fnmatch(k, "*/*.jsonl")}
        assert jsonl
        assert all(jsonl.values())

    @pytest.mark.usefixtures("result")
    def it_reaches_the_api_through_the_credential_proxy(output: Path) -> None:
        log = (output / "credentials.log").read_text()
        assert re.search(r" POST /v1/messages\S* 200 ", log), log

    @pytest.mark.usefixtures("result")
    def it_reaches_for_no_refused_host(output: Path) -> None:
        proxy = (output / "proxy.log").read_text()
        assert refused(proxy) == []


def describe_a_tool_call() -> None:
    @pytest.mark.usefixtures("tool_result")
    def it_is_not_denied(tool_output: Path) -> None:
        assert json.loads((tool_output / "stdout.txt").read_text())["permission_denials"] == []

    @pytest.mark.usefixtures("tool_result")
    def it_writes_into_the_rw_mount(out: Path) -> None:
        assert (out / "pong.txt").read_text().strip() == "pong"
