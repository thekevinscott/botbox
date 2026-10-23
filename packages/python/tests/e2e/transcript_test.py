"""Transcripts stay on disk verbatim, including links and unreadable files."""

import asyncio
from pathlib import Path

import pytest

from botbox import Botbox


def describe_transcripts() -> None:
    def it_keeps_links_without_reading_them(box: Botbox, tmp_path: Path) -> None:
        secret = tmp_path / "secret.jsonl"
        secret.write_text("host secret")
        output = tmp_path / "output"
        projects = "/home/user/.claude/projects"
        result = asyncio.run(box.run(f"ln -s {secret} {projects}/linked.jsonl", output=output))
        assert result.exit_code == 0
        assert (output / "transcripts/linked.jsonl").readlink() == secret
        assert secret.read_text() == "host secret"

    def it_keeps_bad_bytes_and_unreadable_files(box: Botbox, tmp_path: Path) -> None:
        output = tmp_path / "output"
        projects = "/home/user/.claude/projects"
        result = asyncio.run(
            box.run(
                f"printf 'ok \\377\\376' > {projects}/bytes.jsonl; "
                f"echo locked > {projects}/locked.jsonl; chmod 0 {projects}/locked.jsonl",
                output=output,
            )
        )
        assert result.exit_code == 0
        assert (output / "transcripts/bytes.jsonl").read_bytes() == b"ok \xff\xfe"
        locked = output / "transcripts/locked.jsonl"
        try:
            assert locked.stat().st_mode & 0o777 == 0
            with pytest.raises(PermissionError):
                locked.read_text()
        finally:
            locked.chmod(0o600)
