"""`Botbox.run(transcripts=...)` seeds the run's transcripts from an earlier run's folder."""

from pathlib import Path

import pytest
from fake_docker_test import Daemon, volume

from botbox import Botbox


def files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text() for p in sorted(root.rglob("*.jsonl"))}


@pytest.fixture
def earlier(tmp_path: Path) -> Path:
    directory = tmp_path / "earlier"
    (directory / "-old").mkdir(parents=True)
    (directory / "-old" / "old.jsonl").write_text('{"type": "earlier"}\n')
    return directory


def describe_seeded_transcripts() -> None:
    async def it_keeps_the_earlier_sessions_beside_the_new_ones(
        box: Botbox, earlier: Path, tmp_path: Path
    ) -> None:
        output = tmp_path / "output"
        await box.run("true", output=output, transcripts=earlier)
        assert files(output / "transcripts") == {
            "-old/old.jsonl": '{"type": "earlier"}\n',
            "-work/abc.jsonl": '{"type": "user"}\n',
        }

    async def it_leaves_the_source_folder_as_it_was(
        box: Botbox, earlier: Path, tmp_path: Path
    ) -> None:
        await box.run("true", output=tmp_path / "output", transcripts=earlier)
        assert files(earlier) == {"-old/old.jsonl": '{"type": "earlier"}\n'}

    async def it_mounts_the_outputs_copy_over_the_sessions_dir(
        box: Botbox, daemon: Daemon, earlier: Path, tmp_path: Path
    ) -> None:
        output = tmp_path / "output"
        await box.run("true", output=output, transcripts=earlier)
        [run] = daemon.runs("botbox-agent-")
        sessions = f"{box.agent.home}/{box.agent.sessions_dir}"
        assert volume(run, sessions) == (str(output / "transcripts"), "rw")
