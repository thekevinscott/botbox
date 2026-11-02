"""Real Claude and pi runs seeded with an earlier run's transcripts, billed.

Needs ANTHROPIC_API_KEY and OPENROUTER_API_KEY. The first run tells the agent a secret word; each
later run starts from a copy of its transcripts and asks for the word back.
"""

import asyncio
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from conftest import ANTHROPIC_API_KEY, OPENROUTER_API_KEY

from botbox import Botbox, ClaudeAgent, PiAgent

QUESTION = "What secret word did I ask you to remember? Reply with only the word."


def events(output: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (output / "stdout.txt").read_text().splitlines()]


def claude_reply(output: Path) -> str:
    return str(next(e["result"] for e in events(output) if e.get("type") == "result"))


def pi_reply(output: Path) -> str:
    messages = [
        e["message"]
        for e in events(output)
        if e.get("type") == "message_end" and e["message"].get("role") == "assistant"
    ]
    return "".join(part["text"] for part in messages[-1]["content"] if part["type"] == "text")


def sessions(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*.jsonl")}


@dataclass
class Setup:
    box: Botbox
    word: str
    reply: Callable[[Path], str]


@dataclass
class First:
    setup: Setup
    transcripts: Path
    session_id: str


@pytest.fixture(scope="module", params=["claude", "pi"])
def first(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> First:
    """A session that was told a secret word."""
    setup = {
        "claude": lambda: Setup(
            Botbox(ClaudeAgent(api_key=ANTHROPIC_API_KEY)), "marmalade", claude_reply
        ),
        "pi": lambda: Setup(
            Botbox(PiAgent("openrouter", "openai/gpt-4o-mini", api_key=OPENROUTER_API_KEY)),
            "cobalt",
            pi_reply,
        ),
    }[request.param]()
    agent = setup.box.agent
    output = tmp_path_factory.mktemp(f"first-{request.param}")
    prompt = f"Remember the secret word {setup.word}. Reply with only: ok"
    result = asyncio.run(setup.box.run(agent.command(prompt), output=output, workdir=agent.home))
    assert result.exit_code == 0, (output / "stderr.txt").read_text()
    [file] = (output / "transcripts").rglob("*.jsonl")
    session_id = file.stem[-36:]
    UUID(session_id)
    return First(setup, output / "transcripts", session_id)


def seeded(first: First, output: Path, command: str) -> None:
    shutil.copytree(first.transcripts, output / "transcripts")
    box = first.setup.box
    result = asyncio.run(box.run(command, output=output, workdir=box.agent.home))
    assert result.exit_code == 0, (output / "stderr.txt").read_text()


def describe_transcripts() -> None:
    def describe_existing_transcripts() -> None:
        def it_sees_and_keeps_them_and_starts_a_new_session(first: First, tmp_path: Path) -> None:
            agent = first.setup.box.agent
            root = f"{agent.home}/{agent.sessions_dir}"
            seen = "seen.txt"
            command = (
                f"(cd {root} && find . -name '*.jsonl' | cut -c3- | sort > /tmp/{seen})"
                f" && {agent.command(QUESTION)}"
                f" && cp /tmp/{seen} {root}/{seen}"
            )
            seeded(first, tmp_path, command)
            transcripts = tmp_path / "transcripts"
            assert set((transcripts / seen).read_text().split()) == sessions(first.transcripts)
            kept = sessions(transcripts)
            assert sessions(first.transcripts) < kept
            assert len(kept) == len(sessions(first.transcripts)) + 1
            assert first.setup.word not in first.setup.reply(tmp_path).lower()

    def describe_continue() -> None:
        def it_continues_the_latest_session(first: First, tmp_path: Path) -> None:
            seeded(first, tmp_path, first.setup.box.agent.command(QUESTION, resume=True))
            assert first.setup.word in first.setup.reply(tmp_path).lower()

    def describe_resume() -> None:
        def it_resumes_the_session_by_id(first: First, tmp_path: Path) -> None:
            command = first.setup.box.agent.command(QUESTION, resume=first.session_id)
            seeded(first, tmp_path, command)
            assert first.setup.word in first.setup.reply(tmp_path).lower()
