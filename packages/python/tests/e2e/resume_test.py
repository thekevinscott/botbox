"""Real Claude and pi sessions resume from seeded transcripts, billed."""

import asyncio
import json
import shutil
from pathlib import Path
from uuid import UUID

import pytest
from conftest import ANTHROPIC_API_KEY, OPENROUTER_API_KEY

from botbox import Botbox, ClaudeAgent, PiAgent


def reply(output: Path, kind: str) -> str:
    events = [json.loads(line) for line in (output / "stdout.txt").read_text().splitlines()]
    if kind == "claude":
        return next(event["result"] for event in events if event.get("type") == "result")
    messages = [
        event["message"]
        for event in events
        if event.get("type") == "message_end" and event["message"].get("role") == "assistant"
    ]
    return "".join(part["text"] for part in messages[-1]["content"] if part["type"] == "text")


@pytest.fixture(scope="module", params=["claude", "pi"])
def first(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> tuple[Botbox, Path, str, str, str]:
    kind = request.param
    agent = (
        ClaudeAgent(api_key=ANTHROPIC_API_KEY)
        if kind == "claude"
        else PiAgent("openrouter", "openai/gpt-4o-mini", api_key=OPENROUTER_API_KEY)
    )
    word = "marmalade" if kind == "claude" else "cobalt"
    box = Botbox(agent)
    output = tmp_path_factory.mktemp(f"resume-{kind}-first")
    prompt = f"Remember the secret word {word}. Reply with only: ok"
    result = asyncio.run(box.run(agent.command(prompt), output=output, workdir=agent.home))
    assert result.exit_code == 0, (output / "stderr.txt").read_text()
    files = list((output / "transcripts").rglob("*.jsonl"))
    assert len(files) == 1
    session_id = files[0].stem[-36:]
    UUID(session_id)
    return box, output, word, session_id, kind


@pytest.mark.parametrize("mode", ["latest", "id"])
def test_resumes_and_recalls_word(
    first: tuple[Botbox, Path, str, str, str], mode: str, tmp_path: Path
) -> None:
    box, original, word, session_id, kind = first
    output = tmp_path / "resumed"
    shutil.copytree(original / "transcripts", output / "transcripts")
    resume = True if mode == "latest" else session_id
    command = box.agent.command(
        "What secret word did I ask you to remember? Reply with only the word.", resume=resume
    )
    result = asyncio.run(box.run(command, output=output, workdir=box.agent.home))
    assert result.exit_code == 0, (output / "stderr.txt").read_text()
    assert word in reply(output, kind).lower()
