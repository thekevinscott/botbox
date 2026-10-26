"""Keep session diagnostics in the output folder through real Docker teardown, no model calls."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import docker_lines

from botbox import Botbox, ClaudeAgent, RunResult, Session


class ArtifactAgent(ClaudeAgent):
    def session_command(self) -> str:
        return (
            "mkdir -p ~/.claude/projects; "
            "printf 'transcript\\n' > ~/.claude/projects/turn.jsonl; "
            "echo diagnostic >&2; "
            "while read -r line; do "
            'echo \'{"type":"result","result":"ready"}\'; done'
        )


def describe_session_artifacts() -> None:
    @pytest.mark.parametrize("outcome", ["normal", "error", "cancel"])
    async def it_retains_artifacts_and_removes_containers(outcome: str, tmp_path: Path) -> None:
        box = Botbox(ArtifactAgent())
        output = tmp_path / "output"
        temp = tmp_path / "tmp"
        temp.mkdir()
        error = ValueError("caller failed")
        live: Session | None = None
        scratches: list[Path] = []

        async def run() -> None:
            nonlocal live
            async with box.session(output=output) as live:
                scratches.extend(temp.iterdir())
                assert not (scratches[0] / "home").exists()
                assert (await live.message("hi"))[-1]["result"] == "ready"
                if outcome == "error":
                    raise error
                if outcome == "cancel":
                    raise asyncio.CancelledError

        with patch.object(tempfile, "tempdir", str(temp)):
            if outcome == "normal":
                await run()
            else:
                with pytest.raises(ValueError if outcome == "error" else asyncio.CancelledError):
                    await run()
        assert live is not None
        assert live.result == RunResult(0 if outcome == "normal" else -1)
        assert (output / "transcripts" / "turn.jsonl").read_text() == "transcript\n"
        assert "ready" in (output / "stdout.txt").read_text()
        assert (output / "stderr.txt").read_text() == "diagnostic\n"
        [scratch] = scratches
        token = scratch.name.split("-")[1]
        assert not scratch.exists()
        assert docker_lines("ps", "-aq", "--filter", f"label=botbox.run={token}") == []
