"""Transcripts already in `output/transcripts/` are seen by the run and kept beside its own."""

from pathlib import Path

import pytest
from fake_docker_test import Daemon, volume

from botbox import Botbox


def files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text() for p in sorted(root.rglob("*.jsonl"))}


@pytest.fixture
def output(tmp_path: Path) -> Path:
    directory = tmp_path / "output"
    (directory / "transcripts" / "-old").mkdir(parents=True)
    (directory / "transcripts" / "-old" / "old.jsonl").write_text('{"type": "earlier"}\n')
    return directory


def describe_seeded_transcripts() -> None:
    async def it_keeps_the_earlier_sessions_beside_the_new_ones(box: Botbox, output: Path) -> None:
        await box.run("true", output=output)
        assert files(output / "transcripts") == {
            "-old/old.jsonl": '{"type": "earlier"}\n',
            "-work/abc.jsonl": '{"type": "user"}\n',
        }

    async def it_mounts_them_over_the_sessions_dir(
        box: Botbox, daemon: Daemon, output: Path
    ) -> None:
        await box.run("true", output=output)
        [run] = daemon.runs("botbox-agent-")
        sessions = f"{box.agent.home}/{box.agent.sessions_dir}"
        assert volume(run, sessions) == (str(output / "transcripts"), "rw")
