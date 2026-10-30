"""`Botbox.session()` against real Docker and real agents, billed.

Claude uses the host's Claude Code login. Pi and a Codex model (through pi, as CodexAgent has
no session mode) need OPENROUTER_API_KEY, and are skipped without it. The credential proxy sends
every harness's key.
"""

import asyncio
import os
import re
import tempfile
import time
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import refused, transcripts
from run_test import Runs

from botbox import Agent, Botbox, ClaudeAgent, Message, PiAgent, RunResult

# A module global, never a fixture or test argument: pytest prints arguments in tracebacks.
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

TIMEOUT = 240


async def reply_with(replies: AsyncIterator[Message], word: str) -> str:
    """The text of the first reply that says `word`; the agent may say other things first."""
    async with asyncio.timeout(TIMEOUT):
        async for reply in replies:
            if word in reply.text.lower():
                return reply.text
    return ""


def claude() -> Agent:
    return ClaudeAgent(model="claude-opus-5", effort="low")


def pi(model: str) -> Agent:
    if not OPENROUTER_API_KEY:
        pytest.skip("OPENROUTER_API_KEY is not set")
    return PiAgent("openrouter", model, api_key=OPENROUTER_API_KEY)


HARNESSES: dict[str, Callable[[], Agent]] = {
    "claude": claude,
    "pi": lambda: pi("openai/gpt-4o-mini"),
    "codex": lambda: pi("openai/gpt-5.1-codex-mini"),
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
def output(tmp_path_factory: pytest.TempPathFactory, harness: str) -> Path:
    return tmp_path_factory.mktemp(f"output-{harness}")


@dataclass
class Talk:
    """What one session heard: two readers and two callbacks, each open from the start."""

    replies: list[str]
    first: list[Message]
    second: list[Message]
    called_replies: list[Message]
    called_messages: list[Message]
    arrivals: list[float]
    result: RunResult


@pytest.fixture(scope="module")
def talk(harness: str, output: Path) -> Talk:
    """Three messages in one session, each read from its replies, the whole session read too."""
    agent = HARNESSES[harness]()
    box = Botbox(agent)
    called_replies: list[Message] = []
    called_messages: list[Message] = []
    arrivals: list[float] = []

    async def run() -> Talk:
        async with box.session(output=output, timeout=300) as live:
            first, second, replies = live.messages, live.messages, live.replies
            live.on("reply", called_replies.append)
            live.on("message", called_messages.append)
            live.on("message", lambda _: arrivals.append(time.monotonic()))
            await live.send(
                "Remember the codeword heron. Use bash to run exactly:"
                " nohup sh -c 'while true; do date +%s%N > /tmp/beat; sleep 0.2; done'"
                " >/dev/null 2>&1 & Then reply with exactly: started"
            )
            said = [await reply_with(replies, "started")]
            await live.send(
                "Use bash to run exactly:"
                " a=$(cat /tmp/beat); sleep 1; b=$(cat /tmp/beat);"
                ' [ "$a" != "$b" ] && echo ALIVE || echo DEAD'
                " Then reply with exactly what it printed."
            )
            said.append(await reply_with(replies, "alive"))
            await live.send("What codeword did I give you? Reply with the codeword only.")
            said.append(await reply_with(replies, "heron"))
        assert box.result is not None
        return Talk(
            said,
            [message async for message in first],
            [message async for message in second],
            called_replies,
            called_messages,
            arrivals,
            box.result,
        )

    return asyncio.run(run())


def describe_a_session() -> None:
    def it_replies_to_each_message(talk: Talk) -> None:
        assert [reply != "" for reply in talk.replies] == [True] * 3

    def it_keeps_a_background_process_alive_between_messages(talk: Talk) -> None:
        assert "ALIVE" in talk.replies[1]

    def it_keeps_the_conversation_between_messages(talk: Talk) -> None:
        assert "heron" in talk.replies[2].lower()

    def it_gives_both_readers_and_the_message_callback_every_message(talk: Talk) -> None:
        assert talk.first == talk.second == talk.called_messages

    def it_hears_tool_calls_and_results_among_the_messages(harness: str, talk: Talk) -> None:
        agent = HARNESSES[harness]()
        assert {message.type for message in talk.first} >= {agent.MESSAGE_TYPE["ASSISTANT"]}
        assert len({message.type for message in talk.first}) > 1
        assert any(not message.text for message in talk.first)

    def it_calls_back_with_each_reply_and_none_empty(harness: str, talk: Talk) -> None:
        assistant = HARNESSES[harness]().MESSAGE_TYPE["ASSISTANT"]
        mine = [m for m in talk.first if m.type == assistant and m.text]
        assert talk.called_replies == mine
        assert all(reply.text for reply in talk.called_replies)

    def it_hears_messages_as_they_arrive(talk: Talk) -> None:
        assert talk.arrivals[-1] - talk.arrivals[0] > 0.5

    def it_exits_zero_once_the_block_ends(talk: Talk, output: Path) -> None:
        assert talk.result.exit_code == 0, (output / "stderr.txt").read_text()

    def it_leaves_the_transcript_in_output(
        talk: Talk,  # noqa: ARG001
        output: Path,
    ) -> None:
        written = transcripts(output)
        assert written
        assert all(written.values())

    def it_reaches_for_no_refused_host(
        talk: Talk,  # noqa: ARG001
        output: Path,
    ) -> None:
        proxy = (output / "proxy.log").read_text()
        assert refused(proxy) == []

    def it_sends_each_message_through_the_credential_proxy(
        harness: str, talk: Talk, output: Path
    ) -> None:
        path = r"/v1/messages\S*" if harness == "claude" else "/api/v1/chat/completions"
        log = (output / "credentials.log").read_text()
        assert len(re.findall(rf" POST {path} 200 ", log)) >= len(talk.replies), log


def describe_cancelling_mid_reply() -> None:
    async def it_removes_the_sessions_containers_and_home(runs: Runs, tmp_path: Path) -> None:
        box = Botbox(claude())
        output = tmp_path / "output"

        async def talk() -> None:
            async with box.session(output=output) as live:
                messages = live.messages
                await live.send("Use bash to run exactly: sleep 600")
                async for _ in messages:
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
        assert (output / "stdout.txt").read_text()
