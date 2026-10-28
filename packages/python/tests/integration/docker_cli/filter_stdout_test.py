"""An agent's `filter_stdout` against a fake `docker` on PATH, run as a real subprocess."""

from pathlib import Path

import pytest
from fake_docker_test import CopyingClaude, Daemon

from botbox import Botbox, ClaudeAgent

SESSION = ClaudeAgent().session_command()


class FilteringClaude(CopyingClaude):
    """Drops "drop" lines and assistant events, raises on "boom" and renames "keep" to "kept"."""

    def filter_stdout(self, line: bytes) -> bytes | None:
        if line.startswith(b"boom"):
            raise ValueError(line)
        if line == b"drop\n" or b'"assistant"' in line:
            return None
        return line.replace(b"keep", b"kept")


@pytest.fixture
def box(tmp_path: Path) -> Botbox:
    return Botbox(FilteringClaude(api_key="sk-test", host_home=tmp_path / "claude-home"))


@pytest.fixture
def output(tmp_path: Path) -> Path:
    return tmp_path / "output"


def describe_filter_stdout() -> None:
    async def it_writes_only_what_the_filter_keeps_from_a_run(
        box: Botbox, daemon: Daemon, output: Path
    ) -> None:
        daemon.agent("true", stdout="keep\ndrop\nmiddle\ndrop\nkeep last", stderr="drop\n")
        await box.run("true", output=output)
        assert (output / "stdout.txt").read_text() == "kept\nmiddle\nkept last"
        assert (output / "stderr.txt").read_text() == "drop\n"

    async def it_raises_what_the_filter_raises_from_a_run(
        box: Botbox, daemon: Daemon, output: Path
    ) -> None:
        daemon.agent("true", stdout="keep\nboom\nlost\n")
        with pytest.raises(ValueError, match="boom"):
            await box.run("true", output=output)
        assert (output / "stdout.txt").read_text() == "kept\n"

    async def it_reads_session_events_without_the_dropped_lines(
        box: Botbox, daemon: Daemon, output: Path
    ) -> None:
        daemon.agent(SESSION, mode="session", stdout="booting\n")
        async with box.session(output=output) as live:
            first = [event async for event in live.stream("one")]
            second = await live.message("two")
        assert first == [{"type": "result", "result": "ONE"}]
        assert second == [{"type": "result", "result": "TWO"}]
        assert (output / "stdout.txt").read_text() == (
            "booting\n"
            "not json\n"
            '{"type": "result", "result": "ONE"}\n'
            "not json\n"
            '{"type": "result", "result": "TWO"}\n'
        )
