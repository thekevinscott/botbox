"""The API against a fake `docker` on PATH, run as a real subprocess."""

import os
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fake_docker_test import FAKE_DOCKER, CopyingClaude, Daemon

from botbox import Botbox


@pytest.fixture(autouse=True)
def daemon(tmp_path: Path) -> Iterator[Daemon]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "docker"
    fake.write_text(f"#!{sys.executable}\n{FAKE_DOCKER}")
    fake.chmod(0o755)
    state = tmp_path / "daemon"
    state.mkdir()
    env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "FAKE_DOCKER_STATE": str(state)}
    with patch.dict(os.environ, env):
        yield Daemon(state)


@pytest.fixture(autouse=True)
def temp(tmp_path: Path) -> Iterator[Path]:
    """Where the runs' temp homes go."""
    directory = tmp_path / "tmp"
    directory.mkdir()
    with patch.object(tempfile, "tempdir", str(directory)):
        yield directory


@pytest.fixture
def box(tmp_path: Path) -> Botbox:
    return Botbox(CopyingClaude(api_key="sk-test", host_home=tmp_path / "claude-home"))
