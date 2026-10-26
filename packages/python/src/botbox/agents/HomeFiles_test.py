import base64
import io
import tarfile

import pytest

from botbox.agents.HomeFiles import ENV, HomeFiles


def entries(env: dict[str, str]) -> dict[str, tuple[bytes, int, bool]]:
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(env[ENV]))) as archive:
        return {
            entry.name: (
                archive.extractfile(entry).read() if entry.isfile() else b"",  # type: ignore[union-attr]
                entry.mode,
                entry.isfile(),
            )
            for entry in archive.getmembers()
        }


def describe_home_files() -> None:
    def it_passes_nothing_without_files() -> None:
        assert HomeFiles().env() == {}

    def it_carries_each_file_with_its_mode() -> None:
        home = HomeFiles()
        home.write(".claude/.credentials.json", "placeholder", mode=0o600)
        home.write(".claude/settings.json", b"{}")
        assert entries(home.env()) == {
            ".claude/.credentials.json": (b"placeholder", 0o600, True),
            ".claude/settings.json": (b"{}", 0o644, True),
        }

    def it_keeps_the_last_write_to_a_path() -> None:
        home = HomeFiles()
        home.write("a", "first")
        home.write("a", "second")
        assert entries(home.env()) == {"a": (b"second", 0o644, True)}

    def it_refuses_files_too_large_for_docker_to_pass() -> None:
        home = HomeFiles()
        home.write("big", b"x" * 100 * 1024)
        with pytest.raises(ValueError, match="too large"):
            home.env()
