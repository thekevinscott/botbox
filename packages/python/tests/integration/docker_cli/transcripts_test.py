"""Transcripts in `output/transcripts/` reach the agent's sessions dir, with or without resume."""

import json
from pathlib import Path

import pytest
from fake_docker_test import CopyingClaude, Daemon, volume

from botbox import Botbox, PiAgent

PROMPT = "What secret word did I ask you to remember?"


def files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text() for p in sorted(root.rglob("*.jsonl"))}


def pi(home: Path) -> PiAgent:
    home.mkdir()
    (home / "auth.json").write_text("{}")
    (home / "models.json").write_text(
        json.dumps({"providers": {"custom": {"baseUrl": "https://models.example"}}})
    )
    return PiAgent("custom", "m", host_home=home)


@pytest.fixture(params=["claude", "pi"])
def box(request: pytest.FixtureRequest, tmp_path: Path) -> Botbox:
    if request.param == "claude":
        return Botbox(CopyingClaude(api_key="sk-test", host_home=tmp_path / "claude-home"))
    return Botbox(pi(tmp_path / "pi-home"))


@pytest.fixture
def output(tmp_path: Path) -> Path:
    directory = tmp_path / "output"
    (directory / "transcripts" / "-old").mkdir(parents=True)
    (directory / "transcripts" / "-old" / "old.jsonl").write_text('{"type": "earlier"}\n')
    return directory


async def run(box: Botbox, daemon: Daemon, output: Path, command: str) -> list[str]:
    await box.run(command, output=output)
    [container] = daemon.runs("botbox-agent-")
    sessions = f"{box.agent.home}/{box.agent.sessions_dir}"
    assert volume(container, sessions) == (str(output / "transcripts"), "rw")
    assert files(output / "transcripts") == {
        "-old/old.jsonl": '{"type": "earlier"}\n',
        "-work/abc.jsonl": '{"type": "user"}\n',
    }
    return container


def describe_transcripts() -> None:
    def describe_existing_transcripts() -> None:
        async def it_mounts_them_over_the_sessions_dir_and_keeps_them(
            box: Botbox, daemon: Daemon, output: Path
        ) -> None:
            command = box.agent.command(PROMPT)
            container = await run(box, daemon, output, command)
            assert container[-1] == command

    def describe_continue() -> None:
        async def it_runs_the_continue_command_over_them(
            box: Botbox, daemon: Daemon, output: Path
        ) -> None:
            command = box.agent.command(PROMPT, resume=True)
            container = await run(box, daemon, output, command)
            assert container[-1] == command

    def describe_resume() -> None:
        async def it_runs_the_resume_command_over_them(
            box: Botbox, daemon: Daemon, output: Path
        ) -> None:
            command = box.agent.command(PROMPT, resume="old")
            container = await run(box, daemon, output, command)
            assert container[-1] == command
