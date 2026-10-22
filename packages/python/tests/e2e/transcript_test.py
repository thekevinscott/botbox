"""A run that plants symlinks in its transcript folder, aimed at a file only the host can see.

The home is the agent's to write, and botbox moves the transcript out of it on the host.
"""

import asyncio
from pathlib import Path

import pytest
from conftest import transcript

from botbox import Botbox, RunResult

SECRET = "host secret, never in the box"


@pytest.fixture(scope="module")
def secret(tmp_path_factory: pytest.TempPathFactory) -> Path:
    secret = tmp_path_factory.mktemp("host") / "secret.jsonl"
    secret.write_text(SECRET)
    return secret


@pytest.fixture(scope="module")
def result(box: Botbox, secret: Path) -> RunResult:
    projects = "/home/user/.claude/projects"
    return asyncio.run(
        box.run(
            f"mkdir -p {projects}/linked"
            f" && ln -s {secret} {projects}/linked/file.jsonl"
            f" && ln -s {secret.parent} {projects}/dir"
        )
    )


def describe_a_transcript_link_out_of_the_home() -> None:
    def it_planted_the_links(result: RunResult) -> None:
        assert result.exit_code == 0, result.stderr

    def it_keeps_the_host_file_out_of_the_transcript(result: RunResult) -> None:
        assert not any(SECRET in text for text in transcript(result).values())

    @pytest.mark.usefixtures("result")
    def it_leaves_the_host_file_where_it_was(secret: Path) -> None:
        assert secret.read_text() == SECRET


@pytest.fixture(scope="module")
def garbled(box: Botbox) -> RunResult:
    projects = "/home/user/.claude/projects/garbled"
    return asyncio.run(
        box.run(
            f"mkdir -p {projects}"
            f" && printf 'ok \\377\\376' > {projects}/bytes.jsonl"
            f" && echo locked > {projects}/locked.jsonl && chmod 0 {projects}/locked.jsonl"
            " && echo done"
        )
    )


def describe_a_transcript_the_host_cannot_decode_or_open() -> None:
    def it_still_returns_the_run(garbled: RunResult) -> None:
        assert (garbled.exit_code, garbled.stdout) == (0, "done\n")

    def it_keeps_the_bytes_as_written(garbled: RunResult) -> None:
        written = garbled.transcript / ".claude/projects/garbled/bytes.jsonl"
        assert written.read_bytes() == b"ok \377\376"

    def it_keeps_a_file_the_agent_locked_readable(garbled: RunResult) -> None:
        locked = garbled.transcript / ".claude/projects/garbled/locked.jsonl"
        assert locked.read_text() == "locked\n"
