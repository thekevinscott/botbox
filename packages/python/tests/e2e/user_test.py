"""A run as a host uid the image has no passwd entry for."""

import asyncio

import pytest
from conftest import LINE

from botbox import Botbox, ClaudeAgent

UNNAMED = """FROM botbox-claude:latest
USER root
RUN sed -i '/^user:/d' /etc/passwd
USER 1000
"""

PROBES = {
    "whoami": "whoami 2>&1",
    "git": "HOME=/tmp EMAIL=agent@example.com git var GIT_COMMITTER_IDENT >/dev/null 2>&1"
    " && echo ok || echo failed",
}


@pytest.fixture(scope="module")
def report(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    dockerfile = tmp_path_factory.mktemp("unnamed") / "Dockerfile"
    dockerfile.write_text(UNNAMED)
    box = Botbox(ClaudeAgent(), dockerfile=dockerfile)
    script = "".join(LINE.format(name=n, command=c) + "\n" for n, c in PROBES.items())
    result = asyncio.run(box.run(script))
    fields = (line.split("\t", 1) for line in result.stdout.splitlines() if "\t" in line)
    return {name: value.strip() for name, value in fields}


def describe_an_unnamed_host_uid() -> None:
    def it_gets_a_name(report: dict[str, str]) -> None:
        assert report["whoami"] == "user"

    def it_lets_git_find_an_identity(report: dict[str, str]) -> None:
        assert report["git"] == "ok"
