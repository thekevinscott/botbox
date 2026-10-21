"""A run that plants symlinks in its transcript folder, aimed at a file only the host can see.

The home is the agent's to write, and botbox reads the transcript from it on the host.
"""

from pathlib import Path

import pytest

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
    return box.run(
        f"mkdir -p {projects}/linked"
        f" && ln -s {secret} {projects}/linked/file.jsonl"
        f" && ln -s {secret.parent} {projects}/dir"
    )


def describe_a_transcript_link_out_of_the_home() -> None:
    def it_planted_the_links(result: RunResult) -> None:
        assert result.exit_code == 0, result.stderr

    def it_keeps_the_host_file_out_of_the_transcript(result: RunResult) -> None:
        assert not any(SECRET in text for text in result.transcript.values())


@pytest.fixture(scope="module")
def garbled(box: Botbox) -> RunResult:
    projects = "/home/user/.claude/projects/garbled"
    return box.run(
        f"mkdir -p {projects}"
        f" && printf 'ok \\377\\376' > {projects}/bytes.jsonl"
        f" && echo locked > {projects}/locked.jsonl && chmod 0 {projects}/locked.jsonl"
        " && echo done"
    )


def describe_a_transcript_the_host_cannot_decode_or_open() -> None:
    def it_still_returns_the_run(garbled: RunResult) -> None:
        assert (garbled.exit_code, garbled.stdout) == (0, "done\n")

    def it_replaces_the_bad_bytes(garbled: RunResult) -> None:
        assert garbled.transcript[".claude/projects/garbled/bytes.jsonl"] == "ok ��"

    def it_skips_the_file_it_cannot_open(garbled: RunResult) -> None:
        assert ".claude/projects/garbled/locked.jsonl" not in garbled.transcript
