"""A real pi session on OpenRouter, billed. Needs OPENROUTER_API_KEY.

Runs once on the key as `api_key` and once as the host's pi login, an `auth.json` holding it.
The proxy sends the key, the box holds a placeholder. Each run copies its home and environment
into a mount on the way out, and the test scans that and the run's output for the real key.
"""

import asyncio
import json
import os
import re
from pathlib import Path

import pytest
from conftest import leaked, transcripts

from botbox import Botbox, PiAgent, RunResult

# A module global, never a fixture or test argument: pytest prints arguments in tracebacks.
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY is empty")

KEEP = "/keep"


@pytest.fixture(scope="module", params=["api_key", "login"])
def kept(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp(f"kept-{request.param}")


@pytest.fixture(scope="module")
def output(kept: Path) -> Path:
    return kept / "output"


@pytest.fixture(scope="module")
def result(kept: Path, output: Path) -> RunResult:
    if kept.name.startswith("kept-login"):
        pi_home = kept.parent / f"{kept.name}-pi"
        pi_home.mkdir()
        auth = {"openrouter": {"type": "api_key", "key": OPENROUTER_API_KEY}}
        (pi_home / "auth.json").write_text(json.dumps(auth))
        agent = PiAgent("openrouter", "openai/gpt-4o-mini", host_home=pi_home)
    else:
        agent = PiAgent("openrouter", "openai/gpt-4o-mini", api_key=OPENROUTER_API_KEY)
    home = kept / "home"
    home.mkdir()
    command = (
        f"({agent.command('Reply with exactly: pong')}); status=$?;"
        f' cp -a "$HOME/." {KEEP}/home/; env > {KEEP}/env.txt; exit $status'
    )
    box = Botbox(agent)
    return asyncio.run(box.run(command, mounts=[(kept, KEEP, "rw")], output=output))


def describe_a_pi_session_on_openrouter() -> None:
    def it_exits_zero(result: RunResult, output: Path) -> None:
        assert result.exit_code == 0, (output / "stderr.txt").read_text()

    # pi exits 0 on a 401 too, so the reply is what shows the key reached OpenRouter.
    @pytest.mark.usefixtures("result")
    def it_answers(output: Path) -> None:
        assert "pong" in (output / "stdout.txt").read_text()

    @pytest.mark.usefixtures("result")
    def it_keeps_the_final_message_and_the_streaming_updates(output: Path) -> None:
        stdout = (output / "stdout.txt").read_text()
        assert '{"type":"message_end"' in stdout
        assert '{"type":"message_update"' in stdout

    @pytest.mark.usefixtures("result")
    def it_writes_the_transcript(output: Path) -> None:
        transcript = transcripts(output)
        assert transcript
        assert all(transcript.values())

    @pytest.mark.usefixtures("result")
    def it_reaches_openrouter_through_the_credential_proxy(output: Path) -> None:
        log = (output / "credentials.log").read_text()
        assert re.search(r" POST /api/v1/chat/completions 200 ", log), log

    @pytest.mark.usefixtures("result")
    def it_reaches_for_no_host_past_the_credential_proxy(output: Path) -> None:
        proxy = (output / "proxy.log").read_text()
        assert "Established connection" not in proxy
        assert [line for line in proxy.splitlines() if "Proxying refused" in line] == []

    @pytest.mark.usefixtures("result")
    def it_leaves_no_key_in_the_home_env_or_output(kept: Path) -> None:
        assert (kept / "home" / ".pi" / "agent").is_dir()
        assert leaked(kept, OPENROUTER_API_KEY) == []

    @pytest.mark.usefixtures("result")
    def it_gives_pi_a_placeholder_key_and_points_it_at_the_proxy(kept: Path) -> None:
        staged = kept / "home" / ".pi" / "agent"
        auth = json.loads((staged / "auth.json").read_text())
        assert auth == {"openrouter": {"type": "api_key", "key": "sk-or-v1-botbox-placeholder"}}
        models = json.loads((staged / "models.json").read_text())
        assert models == {"providers": {"openrouter": {"baseUrl": "http://127.0.0.1:41894/api/v1"}}}


def describe_a_host_model_with_its_own_base_url() -> None:
    def it_refuses_to_start(tmp_path: Path) -> None:
        (tmp_path / "auth.json").write_text(
            json.dumps({"openrouter": {"type": "api_key", "key": "sk-or-v1-fake"}})
        )
        models = {"providers": {"openrouter": {"models": [{"id": "m", "baseUrl": "http://x"}]}}}
        (tmp_path / "models.json").write_text(json.dumps(models))
        box = Botbox(PiAgent("openrouter", "m", host_home=tmp_path))
        with pytest.raises(ValueError, match="model 'm' sets its own baseUrl"):
            asyncio.run(box.run("true"))
