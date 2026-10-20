"""A live pi session on OpenRouter across several messages, billed. Needs OPENROUTER_API_KEY."""

import os
from collections.abc import Iterator
from typing import Any

import pytest

from botbox import Botbox, PiAgent, RunResult

# A module global, never a fixture or test argument: pytest prints arguments in tracebacks.
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY is empty")

Turns = list[list[dict[str, Any]]]


def reply(events: list[dict[str, Any]]) -> str:
    """The text of the turn's last assistant message."""
    for event in reversed(events):
        message = event.get("message", {})
        if event.get("type") == "message_end" and message.get("role") == "assistant":
            return "".join(part.get("text", "") for part in message["content"])
    return ""


@pytest.fixture(scope="module")
def session() -> Iterator[tuple[Turns, RunResult]]:
    agent = PiAgent("openrouter", "openai/gpt-4o-mini", api_key=OPENROUTER_API_KEY)
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


def describe_a_pi_session_on_openrouter() -> None:
    def it_ends_each_turn_at_agent_end(session: tuple[Turns, RunResult]) -> None:
        turns, _ = session
        assert [turn[-1]["type"] for turn in turns] == ["agent_end"] * 3

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
