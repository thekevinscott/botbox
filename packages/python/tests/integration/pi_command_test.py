"""PiAgent's shell commands run by a real `sh` against a fake `pi` on PATH."""

import json
import os
import shlex
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from botbox import PiAgent

FAKE_PI = """\
import json, os, sys
print(json.dumps({"type": "argv", "argv": sys.argv[1:],
                  "tool_timeout": os.environ.get("BOTBOX_TOOL_TIMEOUT")}), flush=True)
"""


@pytest.fixture(autouse=True)
def pi_on_path(tmp_path: Path) -> Iterator[None]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "fake_pi.py").write_text(FAKE_PI)
    pi = bin_dir / "pi"
    pi.write_text(f'#!/bin/sh\nexec {sys.executable} {bin_dir / "fake_pi.py"} "$@"\n')
    pi.chmod(0o755)
    with patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}):
        yield


@pytest.fixture
def home(tmp_path: Path) -> Path:
    staged = tmp_path / "pi-home"
    staged.mkdir()
    return staged


def provider(home: Path, name: str) -> PiAgent:
    (home / "models.json").write_text(
        json.dumps({"providers": {name: {"baseUrl": "https://models.example"}}})
    )
    return PiAgent(name, "m", host_home=home)


def run(command: str, stdin: str = "") -> tuple[list[Any], int]:
    done = subprocess.run(["sh", "-c", command], input=stdin, capture_output=True, text=True)
    return [json.loads(line) for line in done.stdout.splitlines()], done.returncode


def argv(command: str) -> list[str]:
    events, _ = run(command)
    assert events[0]["type"] == "argv"
    return list(events[0]["argv"])


def describe_quoting() -> None:
    def it_hands_pi_the_prompt_intact() -> None:
        assert argv(PiAgent("openrouter").command("it's $HOME")) == (
            ["-p", "it's $HOME", "--mode", "json"]
        )

    def it_hands_pi_the_provider_intact(home: Path) -> None:
        agent = provider(home, "a b; id")
        assert argv(agent.command("hi"))[-3] == "a b; id"

    def it_hands_pi_the_model_intact() -> None:
        agent = PiAgent("openrouter", "a b; id")
        assert argv(agent.command("hi"))[-2:] == ["--model", "a b; id"]


def describe_appended_flags() -> None:
    def it_hands_pi_flags_a_subclass_appends_to_the_command() -> None:
        class Terse(PiAgent):
            def command(self, prompt: str) -> str:
                return super().command(prompt) + " --append-system-prompt " + shlex.quote("X Y")

        assert argv(Terse("openrouter", "m").command("hi"))[-2:] == [
            "--append-system-prompt",
            "X Y",
        ]


def describe_tool_timeout() -> None:
    @pytest.mark.parametrize("timeout", [0, 2.5])
    def it_passes_the_limit_and_extension_only_when_enabled(timeout: float) -> None:
        events, code = run(PiAgent("openrouter", tool_timeout=timeout).command("hi"))
        assert code == 0
        assert events[0]["tool_timeout"] == ("2.5" if timeout else None)
        if timeout:
            assert events[0]["argv"][-2:] == ["-e", "/usr/local/lib/botbox/tool-timeout.ts"]
        else:
            assert "-e" not in events[0]["argv"]
