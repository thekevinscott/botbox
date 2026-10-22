from pathlib import Path

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

        def it_reads_a_link_that_stays_in_the_home(home: Path) -> None:
            (home / "sessions" / "a.jsonl").write_text("a")
            (home / "sessions" / "b.jsonl").symlink_to(home / "sessions" / "a.jsonl")
            assert read_transcript(home, "sessions/*.jsonl") == {
                "sessions/a.jsonl": "a",
                "sessions/b.jsonl": "a",
            }
