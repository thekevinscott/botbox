import dataclasses
import gc
from pathlib import Path

import pytest

from botbox.RunResult import RunResult


@pytest.fixture
def files(tmp_path: Path) -> Path:
    files = tmp_path / "files"
    (files / "transcript" / ".claude" / "projects").mkdir(parents=True)
    (files / "transcript" / ".claude" / "projects" / "s.jsonl").write_text("{}")
    (files / "proxy.log").write_text("log")
    return files


@pytest.fixture
def result(files: Path) -> RunResult:
    return RunResult("out", "err", 0, "an-image", files)


def describe_run_result() -> None:
    def it_names_its_fields(result: RunResult) -> None:
        assert [f.name for f in dataclasses.fields(result)] == [
            "stdout",
            "stderr",
            "exit_code",
            "image",
            "files",
        ]

    def it_is_frozen(result: RunResult) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.exit_code = 1  # type: ignore[misc]

    def it_keeps_the_transcript_and_proxy_log_in_its_files(
        result: RunResult, files: Path
    ) -> None:
        assert result.transcript == files / "transcript"
        assert (result.transcript / ".claude" / "projects" / "s.jsonl").read_text() == "{}"
        assert result.proxy == files / "proxy.log"
        assert result.proxy.read_text() == "log"

    def it_removes_its_files_when_collected(files: Path) -> None:
        result = RunResult("out", "err", 0, "an-image", files)
        del result
        gc.collect()
        assert not files.exists()

    def it_removes_its_files_on_cleanup(result: RunResult, files: Path) -> None:
        result.cleanup()
        assert not files.exists()
        result.cleanup()

    def it_removes_its_files_when_its_block_ends(result: RunResult, files: Path) -> None:
        with result as entered:
            assert entered is result
            assert files.exists()
        assert not files.exists()

    def it_saves_a_copy_that_outlives_it(result: RunResult, files: Path, tmp_path: Path) -> None:
        saved = result.save(tmp_path / "kept")
        result.cleanup()
        assert saved == tmp_path / "kept"
        assert (saved / "transcript" / ".claude" / "projects" / "s.jsonl").read_text() == "{}"
        assert (saved / "proxy.log").read_text() == "log"

    def it_refuses_to_save_over_an_existing_path(result: RunResult, tmp_path: Path) -> None:
        (tmp_path / "kept").mkdir()
        with pytest.raises(FileExistsError):
            result.save(tmp_path / "kept")
