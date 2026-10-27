import io
import tarfile

from botbox.agents.HomeFiles import HomeFiles


def entries(archive: bytes) -> dict[str, tuple[bytes, int, bool]]:
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        return {
            entry.name: (
                tar.extractfile(entry).read() if entry.isfile() else b"",  # type: ignore[union-attr]
                entry.mode,
                entry.isfile(),
            )
            for entry in tar.getmembers()
        }


def describe_home_files() -> None:
    def it_is_empty_without_files() -> None:
        assert HomeFiles().archive() == b""

    def it_carries_each_file_with_its_mode() -> None:
        home = HomeFiles()
        home.write(".claude/.credentials.json", "placeholder", mode=0o600)
        home.write(".claude/settings.json", b"{}")
        assert entries(home.archive()) == {
            ".claude/.credentials.json": (b"placeholder", 0o600, True),
            ".claude/settings.json": (b"{}", 0o644, True),
        }

    def it_keeps_the_last_write_to_a_path() -> None:
        home = HomeFiles()
        home.write("a", "first")
        home.write("a", "second")
        assert entries(home.archive()) == {"a": (b"second", 0o644, True)}

    def it_is_the_same_for_the_same_files() -> None:
        first, second = HomeFiles(), HomeFiles()
        first.write("a", "content")
        second.write("a", "content")
        assert first.archive() == second.archive()
