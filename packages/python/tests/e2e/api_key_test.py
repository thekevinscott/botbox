"""Claude Code authenticated by an API key, billed. The key is ANTHROPIC_API_KEY, via conftest.

The box holds a placeholder key and the credential proxy sends the real one. The pong run copies
its whole home and environment into a mount on the way out, and the tests scan that and the run's
output for the key.
"""

import asyncio
import json
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import API_KEY, docker_lines, leaked, transcripts

from botbox import Botbox, ClaudeAgent, DockerException, RunResult


@pytest.fixture(scope="module")
def agent() -> ClaudeAgent:
    return ClaudeAgent(model="claude-opus-5", effort="low", api_key=API_KEY)


KEEP = "/keep"


@pytest.fixture(scope="module")
def output(kept: Path) -> Path:
    return kept / "output"


@pytest.fixture(scope="module")
def result(agent: ClaudeAgent, kept: Path, output: Path) -> RunResult:
    (kept / "home").mkdir()
    command = (
        f"{agent.command('Reply with exactly: pong')}; status=$?;"
        f' cp -a "$HOME/." {KEEP}/home/; env > {KEEP}/env.txt; exit $status'
    )
    box = Botbox(agent)
    return asyncio.run(box.run(command, mounts=[(kept, KEEP, "rw")], output=output))


@pytest.fixture(scope="module")
def listing_output(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("listing_output")


@pytest.fixture(scope="module")
def listing(agent: ClaudeAgent, listing_output: Path) -> RunResult:
    """The staged files and the key file's mode, before any CLI runs."""
    command = "find .claude -mindepth 1 | sort; stat -c %a .claude/api_key"
    return asyncio.run(Botbox(agent).run(command, output=listing_output))


@pytest.fixture(scope="module")
def config(agent: ClaudeAgent, tmp_path_factory: pytest.TempPathFactory) -> str:
    """The agent container's `docker inspect`, taken mid-run: the container is gone after.

    Its temp directory, botbox-<token>-*, is the only one in a temp dir of its own.
    """
    output = tmp_path_factory.mktemp("config_output")
    temp = tmp_path_factory.mktemp("tmp")
    with patch.object(tempfile, "tempdir", str(temp)), ThreadPoolExecutor(1) as pool:
        run = pool.submit(asyncio.run, Botbox(agent).run("sleep 5", output=output))
        deadline = time.monotonic() + 120
        while not (started := agents(temp)) and time.monotonic() < deadline:
            time.sleep(0.1)
        (name,) = started
        out = subprocess.run(
            ["docker", "inspect", name], check=True, capture_output=True, text=True
        ).stdout
        run.result()
    return out


def agents(temp: Path) -> set[str]:
    """The running agent containers of the runs whose temp directories are in `temp`."""
    names = {f"botbox-agent-{p.name.split('-')[1]}" for p in temp.iterdir()}
    return names & set(docker_lines("ps", "--format", "{{.Names}}"))


def describe_an_api_key_session() -> None:
    """Leak checks assert a bool so a failure never prints the key."""

    def it_stages_the_key_and_its_helper_only(listing: RunResult, listing_output: Path) -> None:
        assert listing.exit_code == 0, (listing_output / "stderr.txt").read_text()
        assert (listing_output / "stdout.txt").read_text().split() == [
            ".claude/api_key",
            ".claude/projects",
            ".claude/settings.json",
            "600",
        ]

    def it_exits_zero(result: RunResult, output: Path) -> None:
        assert result.exit_code == 0, (output / "stderr.txt").read_text()

    @pytest.mark.usefixtures("result")
    def it_gets_a_reply(output: Path) -> None:
        reply = json.loads((output / "stdout.txt").read_text())
        assert reply["is_error"] is False
        assert "pong" in reply["result"].lower()

    @pytest.mark.usefixtures("result")
    def it_leaves_no_key_in_the_home_env_or_output(kept: Path) -> None:
        assert (kept / "home" / ".claude").is_dir()
        assert leaked(kept, API_KEY) == []

    @pytest.mark.usefixtures("result")
    def it_gives_claude_a_placeholder_key(kept: Path) -> None:
        key = (kept / "home" / ".claude" / "api_key").read_text()
        assert key == "sk-ant-api03-botbox-placeholder"

    @pytest.mark.usefixtures("result")
    def it_points_claude_at_the_credential_proxy(kept: Path) -> None:
        env = (kept / "env.txt").read_text().splitlines()
        assert "ANTHROPIC_BASE_URL=http://127.0.0.1:41894" in env

    @pytest.mark.usefixtures("result")
    def it_sends_the_messages_through_the_credential_proxy(output: Path) -> None:
        lines = (output / "credentials.log").read_text().splitlines()
        assert any(" POST /v1/messages?beta=true 200 " in line for line in lines), lines

    @pytest.mark.usefixtures("result")
    def it_has_tinyproxy_refuse_nothing(output: Path) -> None:
        log = (output / "proxy.log").read_text()
        assert [line for line in log.splitlines() if "Proxying refused" in line] == []

    def it_keeps_the_key_out_of_the_container_config(config: str) -> None:
        leaked = API_KEY in config
        assert not leaked

    def it_keeps_the_key_out_of_a_refused_container(tmp_path: Path) -> None:
        agent = ClaudeAgent(api_key=API_KEY)
        output = tmp_path / "output"
        with pytest.raises(DockerException) as refused:
            asyncio.run(
                Botbox(agent).run("true", mounts=[(tmp_path, "/run/botbox", "rw")], output=output)
            )
        assert refused.value.return_code == 125
        stderr = (output / "stderr.txt").read_text()
        leaked = API_KEY in stderr or API_KEY in str(refused.value)
        assert not leaked

    @pytest.mark.usefixtures("result")
    def it_keeps_the_key_out_of_the_transcript(output: Path) -> None:
        leaked = any(API_KEY in text for text in transcripts(output).values())
        assert not leaked

    @pytest.mark.usefixtures("result")
    def it_keeps_the_key_out_of_the_proxy_log(output: Path) -> None:
        leaked = API_KEY in (output / "proxy.log").read_text()
        assert not leaked
