"""Real Claude Code sessions in the box, billed. Module-scoped: each runs once."""

import json
from collections.abc import Iterator
from fnmatch import fnmatch
from pathlib import Path

import pytest
from conftest import removed

from botbox import Botbox, ClaudeAgent, RunResult


@pytest.fixture(scope="module")
def result() -> Iterator[RunResult]:
    agent = ClaudeAgent(model="claude-opus-5", effort="low")
    yield from removed(Botbox(agent).run(agent.command("Reply with exactly: pong")))


@pytest.fixture(scope="module")
def out(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("out")


@pytest.fixture(scope="module")
def tool_result(out: Path) -> Iterator[RunResult]:
    agent = ClaudeAgent(model="claude-opus-5", effort="low")
    prompt = "Write the text pong to /out/pong.txt using a tool. Do nothing else."
    box = Botbox(agent)
    yield from removed(box.run(agent.command(prompt), mounts=[(out, "/out", "rw")], workdir="/out"))


def describe_a_claude_session() -> None:
    def it_exits_zero(result: RunResult) -> None:
        assert result.exit_code == 0, result.stderr

    def it_reports_no_error(result: RunResult) -> None:
        assert json.loads(result.stdout)["is_error"] is False

    def it_returns_the_transcript(result: RunResult) -> None:
        jsonl = {
            k: v for k, v in result.transcript.items() if fnmatch(k, ".claude/projects/*/*.jsonl")
        }
        assert jsonl
        assert all(jsonl.values())

    def it_reaches_the_api_through_the_proxy(result: RunResult) -> None:
        assert 'Established connection to host "api.anthropic.com"' in result.proxy

    def it_reaches_for_no_refused_host(result: RunResult) -> None:
        refused = [line for line in result.proxy.splitlines() if "Proxying refused" in line]
        assert refused == []


def describe_a_tool_call() -> None:
    def it_is_not_denied(tool_result: RunResult) -> None:
        assert json.loads(tool_result.stdout)["permission_denials"] == []

    def it_writes_into_the_rw_mount(tool_result: RunResult, out: Path) -> None:
        assert tool_result
        assert (out / "pong.txt").read_text().strip() == "pong"
