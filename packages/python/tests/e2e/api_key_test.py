"""Claude Code authenticated by an API key, billed. The key is ANTHROPIC_API_KEY, via conftest."""

import asyncio
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from conftest import API_KEY, docker_lines

from botbox import Botbox, ClaudeAgent, DockerException, RunResult


@pytest.fixture(scope="module")
def agent() -> ClaudeAgent:
    return ClaudeAgent(model="claude-opus-5", effort="low", api_key=API_KEY)


@pytest.fixture(scope="module")
def result(output: Path, agent: ClaudeAgent) -> RunResult:
    return asyncio.run(Botbox(agent).run(agent.command("Reply with exactly: pong"), output=output))


@pytest.fixture(scope="module")
def listing(output: Path, agent: ClaudeAgent) -> RunResult:
    """The staged home and the key file's mode, before any CLI runs."""
    return asyncio.run(
        Botbox(agent).run("find . -mindepth 1 | sort; stat -c %a .claude/api_key", output=output)
    )


@pytest.fixture(scope="module")
def config(output: Path, agent: ClaudeAgent) -> str:
    """The agent container's `docker inspect`, taken mid-run: the container is gone after."""
    before = set(docker_lines("ps", "-a", "--format", "{{.Names}}"))
    with ThreadPoolExecutor(1) as pool:
        run = pool.submit(asyncio.run, Botbox(agent).run("sleep 5", output=output))
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

    def it_stages_the_key_and_its_helper_only(output: Path, listing: RunResult) -> None:
        assert listing.exit_code == 0, (output / "stderr.txt").read_text(errors="replace")
        assert (output / "stdout.txt").read_text(errors="replace").split() == [
            "./.claude",
            "./.claude/api_key",
            "./.claude/projects",
            "./.claude/settings.json",
            "600",
        ]

    def it_exits_zero(output: Path, result: RunResult) -> None:
        assert result.exit_code == 0, (output / "stderr.txt").read_text(errors="replace")

    @pytest.mark.usefixtures("result")
    def it_reports_no_error(
        output: Path,
    ) -> None:
        assert json.loads((output / "stdout.txt").read_text(errors="replace"))["is_error"] is False

    def it_keeps_the_key_out_of_the_container_config(config: str) -> None:
        leaked = API_KEY in config
        assert not leaked

    def it_keeps_the_key_out_of_a_refused_container(output: Path, tmp_path: Path) -> None:
        agent = ClaudeAgent(api_key=API_KEY)
        with pytest.raises(DockerException) as refused:
            asyncio.run(
                Botbox(agent).run("true", mounts=[(tmp_path, "/home/user", "rw")], output=output)
            )
        assert refused.value.return_code == 125
        leaked = API_KEY in refused.value.stderr or API_KEY in str(refused.value)
        assert not leaked

    @pytest.mark.usefixtures("result")
    def it_keeps_the_key_out_of_the_transcript(
        output: Path,
    ) -> None:
        leaked = any(
            API_KEY in text
            for text in {
                str(p.relative_to(output / "transcripts")): p.read_text()
                for p in (output / "transcripts").rglob("*.jsonl")
                if p.is_file()
            }.values()
        )
        assert not leaked

    @pytest.mark.usefixtures("result")
    def it_keeps_the_key_out_of_the_proxy_log(
        output: Path,
    ) -> None:
        leaked = API_KEY in (output / "proxy/tinyproxy.log").read_text(errors="replace")
        assert not leaked
