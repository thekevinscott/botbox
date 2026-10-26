"""A run as a host uid the image has no passwd entry for."""

import asyncio
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from conftest import LINE

from adocker import Image
from botbox import Agent, Botbox, ClaudeAgent, CodexAgent, HomeFiles, PiAgent
from botbox.lockdown import RELAY, lockdown
from botbox.send_home import send_home

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
    output = tmp_path_factory.mktemp("unnamed-output")
    asyncio.run(box.run(script, output=output))
    stdout = (output / "stdout.txt").read_text()
    fields = (line.split("\t", 1) for line in stdout.splitlines() if "\t" in line)
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


def foreign_probes(agent: Agent) -> dict[str, str]:
    """`FOREIGN_PROBES`, plus the owner of a staged file and writes beside and into the
    transcripts mount."""
    files = HomeFiles()
    agent.stage_auth(files)
    staged = next(iter(files.files))
    sessions = f"$HOME/{agent.sessions_dir}"
    return {
        **FOREIGN_PROBES,
        "staged": f'stat -c %u "$HOME/{staged}"',
        "beside": f'touch "$(dirname "{sessions}")/probe" && echo written || echo refused',
        "transcripts": f'touch "{sessions}/probe" && echo written || echo refused',
    }


async def run_as_foreign_uid(box: Botbox, scratch: Path, transcripts: Path) -> str:
    """The agent container's own flags and relay, under a uid and gid the host has no entry for.

    Below `run()`, which always runs as the host's uid. The host can't chown the transcripts
    dir to another uid, so it is world-writable instead.
    """
    image = await box.build()
    token = uuid4().hex[:12]
    probes = foreign_probes(box.agent)
    script = "".join(LINE.format(name=n, command=c) + "\n" for n, c in probes.items())
    target = f"{box.agent.home}/{box.agent.sessions_dir}"
    volumes = [(str(transcripts), target, "rw")]
    async with lockdown((), scratch, token) as jail:
        home = box._home_files()  # noqa: SLF001
        flags = box._lockdown_flags(token, home, jail, volumes, None)  # noqa: SLF001
        flags["user"] = f"{FOREIGN_UID}:{FOREIGN_GID}"
        stdout, stderr = bytearray(), bytearray()
        container = await Image(image).run(
            RELAY,
            "sh",
            "-c",
            script,
            name=f"botbox-agent-{token}",
            rm=True,
            stdin=asyncio.subprocess.PIPE,
            stdout=stdout.extend,
            stderr=stderr.extend,
            **flags,
        )
        stdin = cast("asyncio.StreamWriter", container.stdin)
        await send_home(stdin, home)
        stdin.close()
        code = await container.wait()
    assert code == 0, stderr.decode()
    return stdout.decode()


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
    transcripts = tmp_path_factory.mktemp("transcripts")
    transcripts.chmod(0o777)
    scratch = tmp_path_factory.mktemp("scratch")
    stdout = asyncio.run(run_as_foreign_uid(Botbox(request.param), scratch, transcripts))
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

    def it_gets_the_staged_files(foreign: dict[str, str]) -> None:
        assert foreign["staged"] == str(FOREIGN_UID)

    def it_writes_beside_its_transcripts(foreign: dict[str, str]) -> None:
        assert foreign["beside"] == "written"

    def it_writes_its_transcripts(foreign: dict[str, str]) -> None:
        assert foreign["transcripts"] == "written"
