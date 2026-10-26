"""End-to-end tests: real Docker, real agent calls, nothing mocked. Never run on CI.

Every test drives `botbox` through its public entry point. Docker is only ever read here,
through its own CLI, to see what a run left behind.
"""

import asyncio
import os
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from botbox import Botbox, ClaudeAgent, RunResult

# A module global, never a fixture or test argument: pytest prints arguments in tracebacks.
API_KEY = os.environ["ANTHROPIC_API_KEY"]
if not API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY is empty")

LINE = 'printf "%s\\t" "{name}"; ({command}) 2>&1 | tr "\\n" " "; echo'

Probe = Callable[..., tuple[RunResult, dict[str, str]]]


def docker_lines(*args: str) -> list[str]:
    return subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True
    ).stdout.split()


def leftovers() -> set[str]:
    """Every container, network and host temp directory a botbox run could leave behind."""
    names = docker_lines("ps", "-a", "--format", "{{.Names}}")
    descendants = docker_lines(
        "ps", "-a", "--filter", "ancestor=botbox-claude:latest", "--format", "{{.Names}}"
    )
    networks = docker_lines("network", "ls", "--format", "{{.Name}}")
    temps = Path(tempfile.gettempdir()).glob("botbox-*")
    return {
        *(f"container {n}" for n in names if n.startswith("botbox-")),
        *(f"container {n}" for n in descendants),
        *(f"network {n}" for n in networks if n.startswith("botbox-")),
        *(f"temp {p.name}" for p in temps if p.is_dir()),
    }


@pytest.fixture(scope="session")
def box() -> Botbox:
    """A plain Claude box. Its image is built once up front so `leftovers()` can name it."""
    box = Botbox(ClaudeAgent())
    asyncio.run(box.build())
    return box


@pytest.fixture(scope="session")
def probe(box: Botbox) -> Probe:
    """Run named shell probes in one container; return the result and each probe's output."""

    def run(probes: Mapping[str, str], **options: Any) -> tuple[RunResult, dict[str, str]]:
        script = "".join(LINE.format(name=n, command=c) + "\n" for n, c in probes.items())
        result = asyncio.run(box.run(script, **options))
        fields = (line.split("\t", 1) for line in result.stdout.splitlines() if "\t" in line)
        return result, {name: value.strip() for name, value in fields}

    return run
