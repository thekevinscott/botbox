"""A run as a host uid the image has no passwd entry for."""

import asyncio
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import LINE

from botbox import Botbox, ClaudeAgent, CodexAgent, PiAgent
from botbox.lockdown import RELAY, lockdown

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
def report(output: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    dockerfile = tmp_path_factory.mktemp("unnamed") / "Dockerfile"
    dockerfile.write_text(UNNAMED)
    box = Botbox(ClaudeAgent(), dockerfile=dockerfile)
    script = "".join(LINE.format(name=n, command=c) + "\n" for n, c in PROBES.items())
    result = asyncio.run(box.run(script, output=output))
    assert result.exit_code == 0
    fields = (
        line.split("\t", 1)
        for line in (output / "stdout.txt").read_text(errors="replace").splitlines()
        if "\t" in line
    )
    return {name: value.strip() for name, value in fields}


def describe_an_unnamed_host_uid() -> None:
    def it_gets_a_name(report: dict[str, str]) -> None:
        assert report["whoami"] == "user"

    def it_lets_git_find_an_identity(report: dict[str, str]) -> None:
        assert report["git"] == "ok"


FOREIGN_UID = 1003
FOREIGN_GID = 1005

FOREIGN_PROBES = {
    "whoami": "whoami",
    "uid": "id -u",
    "gid": "id -g",
    "git": "EMAIL=agent@example.com git var GIT_COMMITTER_IDENT >/dev/null 2>&1"
    " && echo ok || echo failed",
    "write": 'echo written >"$HOME/probe" && cat "$HOME/probe"',
}


async def run_as_foreign_uid(box: Botbox, scratch: Path, home: Path) -> str:
    """The agent container's own flags and relay, under a uid and gid the host has no entry for.

    Below `run()`: its per-uid run dir refuses a faked `os.getuid`, and the host can't chown a
    home to another uid, so the home is world-writable instead.
    """
    image = await box.build()
    token = uuid4().hex[:12]
    script = "".join(LINE.format(name=n, command=c) + "\n" for n, c in FOREIGN_PROBES.items())
    async with lockdown((), scratch, token, scratch / "output") as jail:
        flags = box._lockdown_flags(token, home, jail, [], None)  # noqa: SLF001
        flags[flags.index("--user") + 1] = f"{FOREIGN_UID}:{FOREIGN_GID}"
        args = ["docker", "run", "--rm", *flags, image, RELAY, "sh", "-c", script]
        result = await asyncio.to_thread(subprocess.run, args, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.fixture(
    scope="module",
    params=[
        ClaudeAgent(api_key="unused"),
        CodexAgent(api_key="unused"),
        PiAgent("openrouter", api_key="unused"),
    ],
    ids=["claude", "codex", "pi"],
)
def foreign(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> dict[str, str]:
    home = tmp_path_factory.mktemp("home")
    home.chmod(0o777)
    scratch = tmp_path_factory.mktemp("scratch")
    stdout = asyncio.run(run_as_foreign_uid(Botbox(request.param), scratch, home))
    fields = (line.split("\t", 1) for line in stdout.splitlines() if "\t" in line)
    return {name: value.strip() for name, value in fields}


def describe_a_host_uid_and_gid_with_no_entries() -> None:
    def it_gets_a_name(foreign: dict[str, str]) -> None:
        assert foreign["whoami"] == "user"

    def it_keeps_the_uid(foreign: dict[str, str]) -> None:
        assert foreign["uid"] == str(FOREIGN_UID)

    def it_keeps_the_gid(foreign: dict[str, str]) -> None:
        assert foreign["gid"] == str(FOREIGN_GID)

    def it_lets_git_find_an_identity(foreign: dict[str, str]) -> None:
        assert foreign["git"] == "ok"

    def it_writes_under_home(foreign: dict[str, str]) -> None:
        assert foreign["write"] == "written"
