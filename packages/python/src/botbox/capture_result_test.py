import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

from botbox.capture_result import capture_result


@pytest.fixture(autouse=True)
def temp(tmp_path: Path) -> Iterator[Path]:
    directory = tmp_path / "tmp"
    directory.mkdir()
    with patch.object(tempfile, "tempdir", str(directory)):
        yield directory


@pytest.fixture(autouse=True)
def move() -> Iterator[Mock]:
    with patch("botbox.capture_result.move_transcript", autospec=True) as m:
        yield m


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    scratch = tmp_path / "run"
    (scratch / "home").mkdir(parents=True)
    (scratch / "proxy").mkdir()
    (scratch / "proxy" / "tinyproxy.log").write_bytes(b"CONNECT \xff\n")
    return scratch


def made(files: Path) -> Mock:
    return Mock(files=files, transcript=files / "transcript", proxy=files / "proxy.log")


def capture(scratch: Path) -> Any:
    return capture_result(
        made,
        scratch / "home",
        "sessions/*.jsonl",
        scratch / "proxy" / "tinyproxy.log",
    )


def describe_capture_result() -> None:
    def it_makes_the_result_on_its_files(scratch: Path) -> None:
        result = capture(scratch)
        assert result.files.is_dir()

    def it_keeps_its_files_in_a_fresh_dir_under_the_system_temp_dir(
        scratch: Path, temp: Path
    ) -> None:
        result = capture(scratch)
        assert result.files.parent == temp
        assert result.files.stat().st_mode & 0o777 == 0o700

    def it_moves_the_transcript_into_its_files_staged_beside_the_home(
        scratch: Path, move: Mock
    ) -> None:
        result = capture(scratch)
        move.assert_called_once_with(
            scratch / "home", "sessions/*.jsonl", scratch / "transcript", result.transcript
        )

    def it_copies_the_proxy_log_as_written(scratch: Path) -> None:
        result = capture(scratch)
        assert result.proxy.read_bytes() == b"CONNECT \xff\n"
        assert (scratch / "proxy" / "tinyproxy.log").exists()

    def it_warns_and_keeps_an_empty_log_when_it_cannot_copy_it(scratch: Path) -> None:
        (scratch / "proxy" / "tinyproxy.log").unlink()
        with pytest.warns(RuntimeWarning, match="^botbox could not copy its proxy log: "):
            result = capture(scratch)
        assert result.proxy.read_text() == ""

    def it_points_the_warning_at_its_caller(scratch: Path) -> None:
        (scratch / "proxy" / "tinyproxy.log").unlink()
        with pytest.warns(RuntimeWarning) as w:
            capture_result(
                made, scratch / "home", "sessions/*.jsonl", scratch / "proxy" / "tinyproxy.log"
            )
        assert w[0].filename == __file__

    def it_cleans_the_result_up_when_moving_the_transcript_fails(scratch: Path, move: Mock) -> None:
        results: list[Mock] = []

        def make(files: Path) -> Mock:
            results.append(made(files))
            return results[-1]

        move.side_effect = OSError("boom")
        with pytest.raises(OSError, match="boom"):
            capture_result(make, scratch / "home", "*.jsonl", scratch / "proxy" / "tinyproxy.log")
        results[0].cleanup.assert_called_once_with()
