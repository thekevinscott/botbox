"""A real Codex run on the host's ChatGPT login, billed, and one on a fake API key.

The proxy sends the credential; the box holds a placeholder. Each run copies its whole home and
environment into a mount on the way out, and the tests scan that and the run's output for the
real tokens.
"""

import asyncio
import json
from pathlib import Path

import pytest
from conftest import leaked, transcripts

from botbox import Botbox, CodexAgent, RunResult

# Module globals, never fixtures or test arguments: pytest prints arguments in tracebacks.
_TOKENS = json.loads((Path.home() / ".codex" / "auth.json").read_text())["tokens"]
TOKENS: tuple[str, ...] = (_TOKENS["access_token"], _TOKENS["refresh_token"], _TOKENS["id_token"])
del _TOKENS
# OpenAI's 401 names a key by its first 8 and last 4 characters.
FAKE_KEY = "sk-botbox-e2e-not-a-real-key-0123456789"

KEEP = "/keep"


def run_and_keep(agent: CodexAgent, kept: Path) -> RunResult:
    (kept / "home").mkdir()
    command = (
        f"{agent.command('Reply with exactly: pong')}; status=$?;"
        f' cp -a "$HOME/." {KEEP}/home/; env > {KEEP}/env.txt; exit $status'
    )
    box = Botbox(agent)
    return asyncio.run(box.run(command, mounts=[(kept, KEEP, "rw")], output=kept / "output"))


@pytest.fixture(scope="module")
def result(kept: Path) -> RunResult:
    return run_and_keep(CodexAgent("gpt-5.6-luna", "low"), kept)


@pytest.fixture(scope="module")
def keyed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    kept = tmp_path_factory.mktemp("keyed")
    run_and_keep(CodexAgent("gpt-5.6-luna", "low", api_key=FAKE_KEY), kept)
    return kept


def describe_a_codex_run_on_the_host_login() -> None:
    def it_exits_zero(result: RunResult, kept: Path) -> None:
        assert result.exit_code == 0, (kept / "output" / "stderr.txt").read_text()

    @pytest.mark.usefixtures("result")
    def it_completes_the_turn(kept: Path) -> None:
        stdout = (kept / "output" / "stdout.txt").read_text()
        events = [json.loads(line) for line in stdout.splitlines()]
        assert events[-1]["type"] == "turn.completed", stdout

    @pytest.mark.usefixtures("result")
    def it_answers(kept: Path) -> None:
        assert "pong" in (kept / "output" / "stdout.txt").read_text()

    @pytest.mark.usefixtures("result")
    def it_writes_the_transcript(kept: Path) -> None:
        transcript = transcripts(kept / "output")
        assert transcript
        assert all(transcript.values())

    @pytest.mark.usefixtures("result")
    def it_reaches_chatgpt_through_the_credential_proxy(kept: Path) -> None:
        log = (kept / "output" / "credentials.log").read_text()
        assert "POST /backend-api/codex/responses 200" in log

    @pytest.mark.usefixtures("result")
    def it_reaches_for_no_host_past_the_credential_proxy(kept: Path) -> None:
        proxy = (kept / "output" / "proxy.log").read_text()
        assert [line for line in proxy.splitlines() if "Proxying refused" in line] == []

    @pytest.mark.usefixtures("result")
    def it_leaves_no_real_token_in_the_home_env_or_output(kept: Path) -> None:
        assert (kept / "home" / ".codex" / "auth.json").is_file()
        assert [leaked(kept, token) for token in TOKENS] == [[], [], []]

    @pytest.mark.usefixtures("result")
    def it_gives_codex_a_placeholder_login(kept: Path) -> None:
        login = json.loads((kept / "home" / ".codex" / "auth.json").read_text())
        assert login["tokens"]["refresh_token"] == "botbox-placeholder"


def describe_a_codex_run_on_an_api_key() -> None:
    def it_sends_the_key_to_the_openai_api(keyed: Path) -> None:
        stdout = (keyed / "output" / "stdout.txt").read_text()
        assert f"Incorrect API key provided: {FAKE_KEY[:8]}" in stdout
        assert f"{FAKE_KEY[-4:]}. You can find your API key" in stdout

    def it_reaches_the_api_through_the_credential_proxy(keyed: Path) -> None:
        log = (keyed / "output" / "credentials.log").read_text()
        assert "POST /v1/responses 401" in log

    def it_reaches_for_no_host_past_the_credential_proxy(keyed: Path) -> None:
        proxy = (keyed / "output" / "proxy.log").read_text()
        assert [line for line in proxy.splitlines() if "Proxying refused" in line] == []

    def it_leaves_no_key_in_the_home_env_or_output(keyed: Path) -> None:
        assert (keyed / "home" / ".codex" / "auth.json").is_file()
        assert leaked(keyed, FAKE_KEY) == []
