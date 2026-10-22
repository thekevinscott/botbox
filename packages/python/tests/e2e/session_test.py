"""`Botbox.session()` against real Docker and real agents, billed.

Claude uses the host's Claude Code login. Pi and a Codex model (through pi, as CodexAgent has
no session mode) need OPENROUTER_API_KEY, and are skipped without it.
"""

import asyncio
import os
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from conftest import transcript
from run_test import Runs

from botbox import Botbox, ClaudeAgent, PiAgent, RunResult, SessionAgent

# A module global, never a fixture or test argument: pytest prints arguments in tracebacks.
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

Turns = list[list[dict[str, Any]]]


def claude_reply(events: list[dict[str, Any]]) -> str:
    return str(events[-1].get("result", "")) if events else ""


def pi_reply(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        message = event.get("message", {})
        if event.get("type") == "message_end" and message.get("role") == "assistant":
            return "".join(part.get("text", "") for part in message["content"])
    return ""


def claude() -> SessionAgent:
    return ClaudeAgent(model="claude-opus-5", effort="low")


def pi(model: str) -> SessionAgent:
    if not OPENROUTER_API_KEY:
        pytest.skip("OPENROUTER_API_KEY is not set")
    return PiAgent("openrouter", model, api_key=OPENROUTER_API_KEY)


HARNESSES = {
    "claude": (claude, "result", claude_reply),
    "pi": (lambda: pi("openai/gpt-4o-mini"), "agent_end", pi_reply),
    "codex": (lambda: pi("openai/gpt-5.1-codex-mini"), "agent_end", pi_reply),
}


@pytest.fixture(scope="module", params=list(HARNESSES))
def harness(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
def temp(tmp_path: Path) -> Iterator[Path]:
    """This test's own temp dir, so its sessions' homes are told apart from anyone else's."""
    directory = tmp_path / "tmp"
    directory.mkdir()
    with patch.object(tempfile, "tempdir", str(directory)):
        yield directory


@pytest.fixture
def runs(temp: Path) -> Iterator[Runs]:
    runs = Runs(temp)
    yield runs
    runs.clean()


@pytest.fixture(scope="module")
def session(harness: str) -> tuple[Turns, list[float], RunResult]:
    """Three messages in one session; for the first, when each event arrived."""
    make, _, _ = HARNESSES[harness]
    box = Botbox(make())

    async def talk() -> tuple[Turns, list[float], RunResult]:
        async with box.session() as live:
            arrivals, first = [], []
            async for event in live.stream(
                "Remember the codeword heron. Use bash to run exactly:"
                " nohup sh -c 'while true; do date +%s%N > /tmp/beat; sleep 0.2; done'"
                " >/dev/null 2>&1 & Then reply with exactly: started"
            ):
                arrivals.append(time.monotonic())
                first.append(event)
            turns = [
                first,
                await live.message(
                    "Use bash to run exactly:"
                    " a=$(cat /tmp/beat); sleep 1; b=$(cat /tmp/beat);"
                    ' [ "$a" != "$b" ] && echo ALIVE || echo DEAD'
                    " Then reply with exactly what it printed."
                ),
                await live.message("What codeword did I give you? Reply with the codeword only."),
            ]
        assert live.result is not None
        return turns, arrivals, live.result

    return asyncio.run(talk())


def describe_a_session() -> None:
    def it_ends_each_turn_at_the_agents_turn_end(
        harness: str, session: tuple[Turns, list[float], RunResult]
    ) -> None:
        turns, _, _ = session
        _, end, _ = HARNESSES[harness]
        assert [turn[-1]["type"] for turn in turns] == [end] * 3

    def it_has_claude_report_no_error_on_any_turn(
        harness: str, session: tuple[Turns, list[float], RunResult]
    ) -> None:
        if harness != "claude":
            pytest.skip("only Claude's turn end says whether it errored")
        turns, _, _ = session
        assert [turn[-1]["is_error"] for turn in turns] == [False] * 3

    def it_streams_events_before_the_turn_ends(
        session: tuple[Turns, list[float], RunResult],
    ) -> None:
        _, arrivals, _ = session
        assert len(arrivals) > 1
        assert arrivals[-1] - arrivals[0] > 0.5

    def it_keeps_a_background_process_alive_between_messages(
        harness: str, session: tuple[Turns, list[float], RunResult]
    ) -> None:
        turns, _, _ = session
        _, _, reply = HARNESSES[harness]
        assert "ALIVE" in reply(turns[1])

    def it_keeps_the_conversation_between_messages(
        harness: str, session: tuple[Turns, list[float], RunResult]
    ) -> None:
        turns, _, _ = session
        _, _, reply = HARNESSES[harness]
        assert "heron" in reply(turns[2]).lower()

    def it_exits_zero_once_the_block_ends(session: tuple[Turns, list[float], RunResult]) -> None:
        _, _, result = session
        assert result.exit_code == 0, result.stderr

    def it_returns_the_transcript(session: tuple[Turns, list[float], RunResult]) -> None:
        _, _, result = session
        assert transcript(result)
        assert all(transcript(result).values())

    def it_reaches_for_no_refused_host(session: tuple[Turns, list[float], RunResult]) -> None:
        _, _, result = session
        refused = [
            line for line in result.proxy.read_text().splitlines() if "Proxying refused" in line
        ]
        assert refused == []


def describe_cancelling_mid_turn() -> None:
    async def it_removes_the_sessions_containers_and_home(runs: Runs) -> None:
        box = Botbox(claude())

        async def talk() -> None:
            async with box.session() as live:
                async for _ in live.stream("Use bash to run exactly: sleep 600"):
                    pass

        task = asyncio.ensure_future(talk())
        await runs.started()
        await asyncio.sleep(5)
        started = time.monotonic()
        task.cancel()
        await asyncio.wait({task}, timeout=30)
        assert task.cancelled()
        assert time.monotonic() - started < 5
        assert len(runs.tokens) == 1
        assert runs.leftovers() == []
