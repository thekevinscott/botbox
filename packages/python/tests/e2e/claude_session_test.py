"""A live Claude Code session across several messages, billed."""

from collections.abc import Iterator
from typing import Any

import pytest

from botbox import Botbox, ClaudeAgent, RunResult

Turns = list[list[dict[str, Any]]]


def reply(events: list[dict[str, Any]]) -> str:
    """The turn's final text, from its `result` event."""
    return str(events[-1].get("result", "")) if events else ""


@pytest.fixture(scope="module")
def session() -> Iterator[tuple[Turns, RunResult]]:
    agent = ClaudeAgent(model="claude-opus-5", effort="low")
    with Botbox(agent) as box, box.session() as live:
        turns = [
            live.message(
                "Remember the codeword heron. Use bash to run exactly:"
                " nohup sh -c 'while true; do date +%s%N > /tmp/beat; sleep 0.2; done'"
                " >/dev/null 2>&1 & Then reply with exactly: started"
            ),
            live.message(
                "Use bash to run exactly:"
                " a=$(cat /tmp/beat); sleep 1; b=$(cat /tmp/beat);"
                ' [ "$a" != "$b" ] && echo ALIVE || echo DEAD'
                " Then reply with exactly what it printed."
            ),
            live.message("What codeword did I give you? Reply with the codeword only."),
        ]
        result = live.close()
        yield turns, result


def describe_a_claude_session() -> None:
    def it_ends_each_turn_at_the_result(session: tuple[Turns, RunResult]) -> None:
        turns, _ = session
        assert [turn[-1]["type"] for turn in turns] == ["result"] * 3

    def it_reports_no_error(session: tuple[Turns, RunResult]) -> None:
        turns, _ = session
        assert [turn[-1]["is_error"] for turn in turns] == [False] * 3

    def it_keeps_a_background_process_alive_between_messages(
        session: tuple[Turns, RunResult],
    ) -> None:
        turns, _ = session
        assert "ALIVE" in reply(turns[1])

    def it_keeps_the_conversation_between_messages(session: tuple[Turns, RunResult]) -> None:
        turns, _ = session
        assert "heron" in reply(turns[2]).lower()

    def it_exits_zero_once_closed(session: tuple[Turns, RunResult]) -> None:
        _, result = session
        assert result.exit_code == 0, result.stderr

    def it_returns_the_transcript(session: tuple[Turns, RunResult]) -> None:
        _, result = session
        assert result.transcript
        assert all(result.transcript.values())

    def it_reaches_for_no_refused_host(session: tuple[Turns, RunResult]) -> None:
        _, result = session
        refused = [line for line in result.proxy.splitlines() if "Proxying refused" in line]
        assert refused == []
