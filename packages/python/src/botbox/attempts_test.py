from pathlib import Path

from botbox.attempts import clear_attempts, next_attempt, numbered

BASE = ("stdout.txt", "stderr.txt", "proxy.log", "credentials.log")


def touch(folder: Path, *names: str) -> None:
    for name in names:
        (folder / name).touch()


def describe_numbered() -> None:
    def it_finds_each_restart_file_with_its_number(tmp_path: Path) -> None:
        touch(tmp_path, *BASE, "stdout.1.txt", "stderr.2.txt", "proxy.3.log", "credentials.12.log")
        assert {path.name: n for path, n in numbered(tmp_path).items()} == {
            "stdout.1.txt": 1,
            "stderr.2.txt": 2,
            "proxy.3.log": 3,
            "credentials.12.log": 12,
        }

    def it_ignores_other_files(tmp_path: Path) -> None:
        touch(tmp_path, "stdout.x.txt", "proxy.1.txt", "notes.1.txt", "stdout.1.txt.bak")
        (tmp_path / "transcripts").mkdir()
        assert numbered(tmp_path) == {}


def describe_next_attempt() -> None:
    def it_starts_at_one(tmp_path: Path) -> None:
        touch(tmp_path, *BASE)
        assert next_attempt(tmp_path) == 1

    def it_goes_one_past_the_highest(tmp_path: Path) -> None:
        touch(tmp_path, "stdout.1.txt", "proxy.10.log", "stderr.2.txt")
        assert next_attempt(tmp_path) == 11


def describe_clear_attempts() -> None:
    def it_removes_restart_files_and_keeps_the_rest(tmp_path: Path) -> None:
        touch(tmp_path, *BASE, "stdout.1.txt", "credentials.2.log", "notes.txt")
        clear_attempts(tmp_path)
        assert sorted(path.name for path in tmp_path.iterdir()) == sorted((*BASE, "notes.txt"))
