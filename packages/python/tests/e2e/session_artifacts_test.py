"""Keep session diagnostics in the output folder through real Docker teardown, no model calls."""

import asyncio
import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import docker_lines

from botbox import Botbox, ClaudeAgent, RunResult


class ArtifactAgent(ClaudeAgent):
    def session_command(self) -> str:
        return (
            "mkdir -p ~/.claude/projects; "
            "printf 'transcript\\n' > ~/.claude/projects/turn.jsonl; "
            "echo diagnostic >&2; "
            "while read -r line; do "
            'echo \'{"type":"result","result":"ready"}\'; done'
        )


@pytest.fixture
def temp(tmp_path: Path) -> Iterator[Path]:
    """The system temp dir for the test, so the run's own temp dir is the only one in it."""
    temp = tmp_path / "tmp"
    temp.mkdir()
    with patch.object(tempfile, "tempdir", str(temp)):
        yield temp


def describe_session_artifacts() -> None:
    @pytest.mark.parametrize("outcome", ["normal", "error", "cancel"])
    async def it_retains_artifacts_and_removes_containers(
        outcome: str, tmp_path: Path, temp: Path
    ) -> None:
        box = Botbox(ArtifactAgent())
        output = tmp_path / "output"
        error = ValueError("caller failed")
        scratches: list[Path] = []

        async def run() -> None:
            async with box.session(output=output) as live:
                scratches.extend(temp.iterdir())
                assert not (scratches[0] / "home").exists()
                assert (await live.message("hi"))[-1]["result"] == "ready"
                if outcome == "error":
                    raise error
                if outcome == "cancel":
                    raise asyncio.CancelledError

        if outcome == "normal":
            await run()
        else:
            with pytest.raises(ValueError if outcome == "error" else asyncio.CancelledError):
                await run()
        assert box.result == (
            RunResult(0, oom_killed=False) if outcome == "normal" else RunResult(-1)
        )
        assert (output / "transcripts" / "turn.jsonl").read_text() == "transcript\n"
        assert "ready" in (output / "stdout.txt").read_text()
        assert (output / "stderr.txt").read_text() == "diagnostic\n"
        [scratch] = scratches
        token = scratch.name.split("-")[1]
        assert not scratch.exists()
        assert docker_lines("ps", "-aq", "--filter", f"label=botbox.run={token}") == []
