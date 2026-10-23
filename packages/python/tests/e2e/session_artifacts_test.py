"""Retain session diagnostics through real Docker teardown, without model calls."""

import asyncio
from pathlib import Path

import pytest
from conftest import docker_lines

from botbox import Botbox, ClaudeAgent, Session


class ArtifactAgent(ClaudeAgent):
    staged_home: Path

    def stage_auth(self, home: Path) -> None:
        super().stage_auth(home)
        self.staged_home = home

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
    async def it_retains_artifacts_and_removes_containers(output: Path, outcome: str) -> None:
        agent = ArtifactAgent()
        box = Botbox(agent)
        error = ValueError("caller failed")
        live: Session | None = None

        async def run() -> None:
            nonlocal live
            async with box.session(output=output) as live:
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
        assert live is not None
        assert live.result is not None
        assert {
            str(p.relative_to(output / "transcripts")): p.read_text()
            for p in (output / "transcripts").rglob("*.jsonl")
            if p.is_file()
        } == {"turn.jsonl": "transcript\n"}
        assert "ready" in (output / "stdout.txt").read_text(errors="replace")
        assert (output / "stderr.txt").read_text(errors="replace") == "diagnostic\n"
        assert live.result.exit_code == (0 if outcome == "normal" else -1)
        scratch = agent.staged_home.parent
        token = scratch.name
        assert not scratch.exists()
        assert docker_lines("ps", "-aq", "--filter", f"label=botbox.run={token}") == []
