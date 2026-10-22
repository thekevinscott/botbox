"""Claude Code authenticated by an API key, billed. The key is ANTHROPIC_API_KEY, via conftest."""

import asyncio
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from conftest import API_KEY, docker_lines, transcript

from botbox import Botbox, ClaudeAgent, DockerException, RunResult


@pytest.fixture(scope="module")
def agent() -> ClaudeAgent:
    return ClaudeAgent(model="claude-opus-5", effort="low", api_key=API_KEY)


@pytest.fixture(scope="module")
def result(agent: ClaudeAgent) -> RunResult:
    return asyncio.run(Botbox(agent).run(agent.command("Reply with exactly: pong")))


@pytest.fixture(scope="module")
def listing(agent: ClaudeAgent) -> RunResult:
    """The staged home and the key file's mode, before any CLI runs."""
    return asyncio.run(Botbox(agent).run("find . -mindepth 1 | sort; stat -c %a .claude/api_key"))


@pytest.fixture(scope="module")
def config(agent: ClaudeAgent) -> str:
    """The agent container's `docker inspect`, taken mid-run: the container is gone after."""
    before = set(docker_lines("ps", "-a", "--format", "{{.Names}}"))
    with ThreadPoolExecutor(1) as pool:
        run = pool.submit(asyncio.run, Botbox(agent).run("sleep 5"))
        deadline = time.monotonic() + 120
        while not (started := agents() - before) and time.monotonic() < deadline:
            time.sleep(0.1)
        (name,) = started
        out = subprocess.run(
            ["docker", "inspect", name], check=True, capture_output=True, text=True
        ).stdout
        run.result()
    return out


def agents() -> set[str]:
    return {
        n for n in docker_lines("ps", "--format", "{{.Names}}") if n.startswith("botbox-agent-")
    }


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

    def it_keeps_the_key_out_of_the_container_config(config: str) -> None:
        leaked = API_KEY in config
        assert not leaked

    def it_keeps_the_key_out_of_a_refused_container(tmp_path: Path) -> None:
        agent = ClaudeAgent(api_key=API_KEY)
        with pytest.raises(DockerException) as refused:
            asyncio.run(Botbox(agent).run("true", mounts=[(tmp_path, "/home/user", "rw")]))
        assert refused.value.return_code == 125
        leaked = API_KEY in refused.value.stderr or API_KEY in str(refused.value)
        assert not leaked

    def it_keeps_the_key_out_of_the_transcript(result: RunResult) -> None:
        leaked = any(API_KEY in text for text in transcript(result).values())
        assert not leaked

    def it_keeps_the_key_out_of_the_proxy_log(result: RunResult) -> None:
        leaked = API_KEY in result.proxy.read_text()
        assert not leaked
