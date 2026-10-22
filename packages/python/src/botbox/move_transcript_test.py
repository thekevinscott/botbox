import shutil
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from botbox.move_transcript import move_transcript


@pytest.fixture
def home(tmp_path: Path) -> Path:
    (tmp_path / "home" / "sessions").mkdir(parents=True)
    return tmp_path / "home"


@pytest.fixture
def staging(tmp_path: Path) -> Path:
    return tmp_path / "staging"


@pytest.fixture
def dest(tmp_path: Path) -> Path:
    return tmp_path / "dest"


@pytest.fixture
def host(tmp_path: Path) -> Path:
    host = tmp_path / "host"
    host.mkdir()
    (host / "a.jsonl").write_text("host secret")
    return host


def kept(dest: Path) -> dict[str, str]:
    return {
        path.relative_to(dest).as_posix(): path.read_text()
        for path in sorted(dest.rglob("*"))
        if path.is_file()
    }


def describe_move_transcript() -> None:
    def it_moves_matching_files_keeping_their_paths_relative_to_the_home(
        home: Path, staging: Path, dest: Path
    ) -> None:
        (home / "sessions" / "b.jsonl").write_text("b")
        (home / "sessions" / "a.jsonl").write_text("a")
        (home / "sessions" / "notes.txt").write_text("x")
        move_transcript(home, "sessions/*.jsonl", staging, dest)
        assert kept(dest) == {"sessions/a.jsonl": "a", "sessions/b.jsonl": "b"}
        assert sorted(p.name for p in (home / "sessions").iterdir()) == ["notes.txt"]

    def it_makes_an_empty_transcript_when_nothing_matches(
        home: Path, staging: Path, dest: Path
    ) -> None:
        move_transcript(home, "sessions/*.jsonl", staging, dest)
        assert dest.is_dir()
        assert list(dest.iterdir()) == []

    def it_keeps_the_bytes_as_written(home: Path, staging: Path, dest: Path) -> None:
        (home / "a.jsonl").write_bytes(b"ok \xff\xfe")
        move_transcript(home, "*.jsonl", staging, dest)
        assert (dest / "a.jsonl").read_bytes() == b"ok \xff\xfe"

    def it_skips_directories_that_match(home: Path, staging: Path, dest: Path) -> None:
        (home / "sessions" / "dir.jsonl").mkdir()
        move_transcript(home, "sessions/*.jsonl", staging, dest)
        assert list(dest.iterdir()) == []

    def describe_a_link_planted_by_the_agent() -> None:
        def it_skips_a_file_link_and_leaves_its_target(
            home: Path, staging: Path, dest: Path, host: Path
        ) -> None:
            (home / "sessions" / "a.jsonl").symlink_to(host / "a.jsonl")
            move_transcript(home, "sessions/*.jsonl", staging, dest)
            assert kept(dest) == {}
            assert (host / "a.jsonl").read_text() == "host secret"

        def it_skips_a_link_that_stays_in_the_home(home: Path, staging: Path, dest: Path) -> None:
            (home / "sessions" / "a.jsonl").write_text("a")
            (home / "sessions" / "b.jsonl").symlink_to(home / "sessions" / "a.jsonl")
            move_transcript(home, "sessions/*.jsonl", staging, dest)
            assert kept(dest) == {"sessions/a.jsonl": "a"}

        def it_moves_nothing_through_a_directory_link(
            home: Path, staging: Path, dest: Path, host: Path
        ) -> None:
            (home / "sessions" / "host").symlink_to(host)
            move_transcript(home, "sessions/*/*.jsonl", staging, dest)
            assert kept(dest) == {}
            assert (host / "a.jsonl").read_text() == "host secret"

        @pytest.fixture
        def swapped(home: Path, host: Path) -> Iterator[None]:
            """The agent swaps its sessions dir for a link to `host` once the glob has listed."""
            (home / "sessions" / "a.jsonl").write_text("a")
            original = Path.glob

            def glob(path: Path, pattern: str) -> Iterator[Path]:
                found = list(original(path, pattern))
                shutil.rmtree(home / "sessions")
                (home / "sessions").symlink_to(host)
                return iter(found)

            with patch("pathlib.Path.glob", autospec=True, side_effect=glob):
                yield

        @pytest.mark.usefixtures("swapped")
        def it_moves_nothing_from_a_dir_swapped_for_a_link_after_the_glob(
            home: Path, staging: Path, dest: Path, host: Path
        ) -> None:
            move_transcript(home, "sessions/*.jsonl", staging, dest)
            assert kept(dest) == {}
            assert (host / "a.jsonl").read_text() == "host secret"

        @pytest.fixture
        def relinked(home: Path, host: Path) -> Iterator[None]:
            """The agent swaps a matched file for a link to `host` once the glob has listed."""
            (home / "sessions" / "a.jsonl").write_text("a")
            original = Path.glob

            def glob(path: Path, pattern: str) -> Iterator[Path]:
                found = list(original(path, pattern))
                (home / "sessions" / "a.jsonl").unlink()
                (home / "sessions" / "a.jsonl").symlink_to(host / "a.jsonl")
                return iter(found)

            with patch("pathlib.Path.glob", autospec=True, side_effect=glob):
                yield

        @pytest.mark.usefixtures("relinked")
        def it_skips_a_file_swapped_for_a_link_after_the_glob(
            home: Path, staging: Path, dest: Path, host: Path
        ) -> None:
            move_transcript(home, "sessions/*.jsonl", staging, dest)
            assert kept(dest) == {}
            assert (host / "a.jsonl").read_text() == "host secret"
