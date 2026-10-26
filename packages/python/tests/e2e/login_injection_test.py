"""A Claude run on the host's login: the proxy sends the token, the box never holds it.

The run copies its whole home and environment into a mount on the way out, and the test scans
that and the run's output for the host's real tokens.
"""

import asyncio
import json
from pathlib import Path

import pytest
from conftest import leaked

from botbox import Botbox, ClaudeAgent, RunResult

# Module globals, never fixtures or test arguments: pytest prints arguments in tracebacks.
_LOGIN = json.loads((Path.home() / ".claude" / ".credentials.json").read_text())["claudeAiOauth"]
ACCESS_TOKEN: str = _LOGIN["accessToken"]
REFRESH_TOKEN: str = _LOGIN["refreshToken"]
del _LOGIN

KEEP = "/keep"


@pytest.fixture(scope="module")
def result(kept: Path) -> RunResult:
    home = kept / "home"
    home.mkdir()
    agent = ClaudeAgent(model="claude-opus-5", effort="low")
    command = (
        f"{agent.command('Reply with exactly: pong')}; status=$?;"
        f' cp -a "$HOME/." {KEEP}/home/; env > {KEEP}/env.txt; exit $status'
    )
    box = Botbox(agent)
    return asyncio.run(box.run(command, mounts=[(kept, KEEP, "rw")], output=kept / "output"))


def describe_a_run_on_the_host_login() -> None:
    def it_gets_a_reply(result: RunResult, kept: Path) -> None:
        assert result.exit_code == 0, (kept / "output" / "stderr.txt").read_text()
        reply = json.loads((kept / "output" / "stdout.txt").read_text())
        assert reply["is_error"] is False
        assert "pong" in reply["result"].lower()

    @pytest.mark.usefixtures("result")
    def it_leaves_no_access_token_in_the_home_env_or_output(kept: Path) -> None:
        assert (kept / "home" / ".claude").is_dir()
        assert leaked(kept, ACCESS_TOKEN) == []

    @pytest.mark.usefixtures("result")
    def it_leaves_no_refresh_token_in_the_home_env_or_output(kept: Path) -> None:
        assert leaked(kept, REFRESH_TOKEN) == []

    @pytest.mark.usefixtures("result")
    def it_gives_claude_a_placeholder_login(kept: Path) -> None:
        login = json.loads((kept / "home" / ".claude" / ".credentials.json").read_text())
        assert login["claudeAiOauth"]["accessToken"].startswith("sk-ant-oat01-botbox-")

    @pytest.mark.usefixtures("result")
    def it_points_claude_at_the_credential_proxy(kept: Path) -> None:
        env = (kept / "env.txt").read_text().splitlines()
        assert "ANTHROPIC_BASE_URL=http://127.0.0.1:41894" in env
