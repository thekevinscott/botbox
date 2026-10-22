import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from botbox.capture_result import capture_result
from botbox.RunResult import RunResult


@pytest.fixture(autouse=True)
def temp(tmp_path: Path) -> Iterator[Path]:
    directory = tmp_path / "tmp"
    directory.mkdir()
    with patch.object(tempfile, "tempdir", str(directory)):
        yield directory


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    scratch = tmp_path / "run"
    (scratch / "home" / "sessions").mkdir(parents=True)
    (scratch / "home" / "sessions" / "a.jsonl").write_text("a")
    (scratch / "proxy").mkdir()
    (scratch / "proxy" / "tinyproxy.log").write_bytes(b"CONNECT \xff\n")
    return scratch


def capture(scratch: Path) -> RunResult:
    return capture_result(
        "out",
        "err",
        3,
        "an-image",
        scratch / "home",
        "sessions/*.jsonl",
        scratch / "proxy" / "tinyproxy.log",
    )


def describe_capture_result() -> None:
    def it_holds_the_output_exit_code_and_image(scratch: Path) -> None:
        result = capture(scratch)
        assert (result.stdout, result.stderr, result.exit_code, result.image) == (
            "out",
            "err",
            3,
            "an-image",
        )

    def it_keeps_its_files_in_a_fresh_dir_under_the_system_temp_dir(
        scratch: Path, temp: Path
    ) -> None:
        result = capture(scratch)
        assert result.files.parent == temp
        assert result.files.stat().st_mode & 0o777 == 0o700

    def it_moves_the_transcript_out_of_the_home(scratch: Path) -> None:
        result = capture(scratch)
        assert (result.transcript / "sessions" / "a.jsonl").read_text() == "a"
        assert not (scratch / "home" / "sessions" / "a.jsonl").exists()

    def it_stages_the_transcript_beside_the_home(scratch: Path) -> None:
        (scratch / "home" / "sessions" / "b.jsonl").symlink_to("a.jsonl")
        capture(scratch)
        assert [p.is_symlink() for p in (scratch / "transcript").iterdir()] == [True]

    def it_copies_the_proxy_log_as_written(scratch: Path) -> None:
        result = capture(scratch)
        assert result.proxy.read_bytes() == b"CONNECT \xff\n"
        assert (scratch / "proxy" / "tinyproxy.log").exists()

    def it_warns_and_keeps_an_empty_log_when_it_cannot_copy_it(scratch: Path) -> None:
        (scratch / "proxy" / "tinyproxy.log").unlink()
        with pytest.warns(RuntimeWarning, match="^botbox could not copy its proxy log: "):
            result = capture(scratch)
        assert result.proxy.read_text() == ""

    def it_removes_its_dir_when_moving_the_transcript_fails(scratch: Path, temp: Path) -> None:
        with (
            patch("botbox.capture_result.move_transcript", side_effect=OSError("boom")),
            pytest.raises(OSError, match="boom"),
        ):
            capture(scratch)
        assert list(temp.iterdir()) == []
