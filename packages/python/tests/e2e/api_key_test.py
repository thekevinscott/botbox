"""Claude Code authenticated by an API key, billed. The key is ANTHROPIC_API_KEY, via conftest."""

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import API_KEY, removed
from python_on_whales.exceptions import DockerException

from botbox import Botbox, ClaudeAgent, RunResult


@pytest.fixture(scope="module")
def agent() -> ClaudeAgent:
    return ClaudeAgent(model="claude-opus-5", effort="low", api_key=API_KEY)


@pytest.fixture(scope="module")
def result(agent: ClaudeAgent) -> Iterator[RunResult]:
    yield from removed(Botbox(agent).run(agent.command("Reply with exactly: pong")))


@pytest.fixture(scope="module")
def listing(agent: ClaudeAgent) -> Iterator[RunResult]:
    """The staged home and the key file's mode, before any CLI runs."""
    yield from removed(Botbox(agent).run("find . -mindepth 1 | sort; stat -c %a .claude/api_key"))


def inspect(container: str) -> str:
    return subprocess.run(
        ["docker", "inspect", container], check=True, capture_output=True, text=True
    ).stdout


def describe_an_api_key_session() -> None:
    """Leak checks assert a bool so a failure never prints the key."""

    def it_stages_the_key_and_its_helper_only(listing: RunResult) -> None:
        assert listing.exit_code == 0, listing.stderr
        assert listing.stdout.split() == [
            "./.claude",
            "./.claude/api_key",
            "./.claude/settings.json",
            "600",
        ]

    def it_exits_zero(result: RunResult) -> None:
        assert result.exit_code == 0, result.stderr

    def it_reports_no_error(result: RunResult) -> None:
        assert json.loads(result.stdout)["is_error"] is False

    def it_keeps_the_key_out_of_the_container_config(listing: RunResult) -> None:
        leaked = API_KEY in inspect(listing.container)
        assert not leaked

    def it_keeps_the_key_out_of_a_failed_create(tmp_path: Path) -> None:
        agent = ClaudeAgent(api_key=API_KEY)
        with pytest.raises(DockerException) as failure:
            Botbox(agent).run("true", mounts=[(tmp_path, "/home/node", "rw")])
        leaked = API_KEY in str(failure.value)
        assert not leaked

    def it_keeps_the_key_out_of_the_transcript(result: RunResult) -> None:
        leaked = any(API_KEY in text for text in result.transcript.values())
        assert not leaked

    def it_keeps_the_key_out_of_the_proxy_log(result: RunResult) -> None:
        leaked = API_KEY in result.proxy
        assert not leaked
