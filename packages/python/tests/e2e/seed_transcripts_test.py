"""A real pi run on OpenRouter, seeded with an earlier run's transcripts, billed.

Needs OPENROUTER_API_KEY. The first run writes a session; the second, whose output starts with a
copy of those transcripts, lists the sessions it can see before pi starts its own.
"""

import asyncio
import shutil
from pathlib import Path

import pytest
from conftest import OPENROUTER_API_KEY

from botbox import Botbox, PiAgent


def sessions(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*.jsonl")}


@pytest.fixture(scope="module")
def box() -> Botbox:
    return Botbox(PiAgent("openrouter", "openai/gpt-4o-mini", api_key=OPENROUTER_API_KEY))


@pytest.fixture(scope="module")
def first(box: Botbox, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A pi session on OpenRouter, written to the first run's transcripts."""
    output = tmp_path_factory.mktemp("first")
    command = box.agent.command("Reply with exactly: pong")
    result = asyncio.run(box.run(command, output=output))
    assert result.exit_code == 0, (output / "stderr.txt").read_text()
    assert "pong" in (output / "stdout.txt").read_text()
    assert sessions(output / "transcripts"), "pi wrote no session under sessions_dir"
    return output / "transcripts"


@pytest.fixture(scope="module")
def second(box: Botbox, first: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A run seeded from `first` that lists the sessions it can see, then starts its own."""
    output = tmp_path_factory.mktemp("second")
    shutil.copytree(first, output / "transcripts")
    root = f"{box.agent.home}/{box.agent.sessions_dir}"
    command = (
        f"(cd {root} && find . -name '*.jsonl' | cut -c3- | sort > /tmp/seen)"
        f" && ({box.agent.command('Reply with exactly: pong')}) > /dev/null"
        " && cat /tmp/seen"
    )
    result = asyncio.run(box.run(command, output=output))
    assert result.exit_code == 0, (output / "stderr.txt").read_text()
    return output


def describe_a_seeded_pi_run() -> None:
    def it_sees_the_earlier_sessions_under_sessions_dir(first: Path, second: Path) -> None:
        seen = set((second / "stdout.txt").read_text().split())
        assert seen == sessions(first)

    def it_keeps_the_earlier_sessions_and_adds_its_own(first: Path, second: Path) -> None:
        kept = sessions(second / "transcripts")
        assert sessions(first) < kept
