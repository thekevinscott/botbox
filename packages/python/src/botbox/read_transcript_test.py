import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from botbox.read_transcript import read_transcript


def describe_read_transcript() -> None:
    def it_reads_matching_files_by_path_relative_to_the_home(tmp_path: Path) -> None:
        (tmp_path / "sessions").mkdir()
        (tmp_path / "sessions" / "b.jsonl").write_text("b")
        (tmp_path / "sessions" / "a.jsonl").write_text("a")
        (tmp_path / "sessions" / "notes.txt").write_text("x")
        assert read_transcript(tmp_path, "sessions/*.jsonl") == {
            "sessions/a.jsonl": "a",
            "sessions/b.jsonl": "b",
        }

    def it_skips_directories_that_match(tmp_path: Path) -> None:
        (tmp_path / "sessions" / "dir.jsonl").mkdir(parents=True)
        assert read_transcript(tmp_path, "sessions/*.jsonl") == {}

    def it_replaces_bytes_that_are_not_utf8(tmp_path: Path) -> None:
        (tmp_path / "a.jsonl").write_bytes(b"ok \xff\xfe")
        assert read_transcript(tmp_path, "*.jsonl") == {"a.jsonl": "ok ��"}

    def it_skips_a_file_it_cannot_open(tmp_path: Path) -> None:
        (tmp_path / "a.jsonl").write_text("a")
        (tmp_path / "b.jsonl").write_text("b")
        (tmp_path / "b.jsonl").chmod(0)
        assert read_transcript(tmp_path, "*.jsonl") == {"a.jsonl": "a"}

    def describe_a_symlink_planted_by_the_agent() -> None:
        @pytest.fixture
        def home(tmp_path: Path) -> Path:
            (tmp_path / "home" / "sessions").mkdir(parents=True)
            return tmp_path / "home"

        @pytest.fixture
        def secret(tmp_path: Path) -> Path:
            secret = tmp_path / "host" / "secret.jsonl"
            secret.parent.mkdir()
            secret.write_text("host secret")
            return secret

        def it_skips_a_file_link_out_of_the_home(home: Path, secret: Path) -> None:
            (home / "sessions" / "a.jsonl").symlink_to(secret)
            assert read_transcript(home, "sessions/*.jsonl") == {}

        def it_skips_a_directory_link_out_of_the_home(home: Path, secret: Path) -> None:
            (home / "sessions" / "host").symlink_to(secret.parent)
            assert read_transcript(home, "sessions/*/*.jsonl") == {}

        def it_skips_a_link_that_stays_in_the_home(home: Path) -> None:
            (home / "sessions" / "a.jsonl").write_text("a")
            (home / "sessions" / "b.jsonl").symlink_to(home / "sessions" / "a.jsonl")
            assert read_transcript(home, "sessions/*.jsonl") == {"sessions/a.jsonl": "a"}

        def it_skips_a_fifo(home: Path) -> None:
            os.mkfifo(home / "sessions" / "a.jsonl")
            assert read_transcript(home, "sessions/*.jsonl") == {}

        def describe_a_link_swapped_in_while_reading() -> None:
            @pytest.fixture(params=["glob", "resolve"])
            def swap(
                request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, home: Path
            ) -> list[Path]:
                swaps: list[Path] = []
                original = getattr(Path, request.param)

                def then_swap(self: Path, *args: Any) -> Any:
                    result = original(self, *args)
                    while swaps and self != home:
                        link, target = swaps.pop(0), swaps.pop(0)
                        shutil.rmtree(link) if link.is_dir() else link.unlink()
                        link.symlink_to(target)
                    return result

                monkeypatch.setattr(Path, request.param, then_swap)
                return swaps

            def it_skips_a_file_swapped_for_a_link_out_of_the_home(
                home: Path, secret: Path, swap: list[Path]
            ) -> None:
                (home / "sessions" / "a.jsonl").write_text("a")
                swap += [home / "sessions" / "a.jsonl", secret]
                assert "host secret" not in read_transcript(home, "sessions/*.jsonl").values()

            def it_skips_a_directory_swapped_for_a_link_out_of_the_home(
                home: Path, secret: Path, swap: list[Path]
            ) -> None:
                (home / "sessions" / "host").mkdir()
                (home / "sessions" / "host" / "secret.jsonl").write_text("a")
                swap += [home / "sessions" / "host", secret.parent]
                assert "host secret" not in read_transcript(home, "sessions/*/*.jsonl").values()
