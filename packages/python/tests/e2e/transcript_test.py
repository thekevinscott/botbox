"""What an agent leaves in its transcript folder stays on disk in output/transcripts/ as written.

Links aimed at host files stay links, and bytes the host cannot decode or open are kept as is.
"""

import asyncio
from pathlib import Path

import pytest

from botbox import Botbox

PROJECTS = "/home/user/.claude/projects"


def describe_a_transcript_link_out_of_the_home() -> None:
    def it_stays_a_link_without_reading_its_target(box: Botbox, tmp_path: Path) -> None:
        secret = tmp_path / "secret.jsonl"
        secret.write_text("host secret, never in the box")
        output = tmp_path / "output"
        result = asyncio.run(box.run(f"ln -s {secret} {PROJECTS}/linked.jsonl", output=output))
        assert result.exit_code == 0, (output / "stderr.txt").read_text()
        assert (output / "transcripts" / "linked.jsonl").readlink() == secret
        assert secret.read_text() == "host secret, never in the box"


def describe_a_transcript_the_host_cannot_decode_or_open() -> None:
    def it_keeps_the_files_as_written(box: Botbox, tmp_path: Path) -> None:
        output = tmp_path / "output"
        result = asyncio.run(
            box.run(
                f"printf 'ok \\377\\376' > {PROJECTS}/bytes.jsonl"
                f" && echo locked > {PROJECTS}/locked.jsonl && chmod 0 {PROJECTS}/locked.jsonl",
                output=output,
            )
        )
        assert result.exit_code == 0, (output / "stderr.txt").read_text()
        assert (output / "transcripts" / "bytes.jsonl").read_bytes() == b"ok \xff\xfe"
        locked = output / "transcripts" / "locked.jsonl"
        try:
            assert locked.stat().st_mode & 0o777 == 0
            with pytest.raises(PermissionError):
                locked.read_text()
        finally:
            locked.chmod(0o600)
