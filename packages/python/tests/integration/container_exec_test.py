"""`Container.exec` against a fake `docker` that prints far more than one chunk."""

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from adocker import Container, DockerException

LOUD = """
import os, sys
for _ in range(128):
    os.write(1, b"x" * 65536)
os.write(2, b"done\\n")
sys.exit(int(os.environ.get("FAKE_EXEC_CODE", "0")))
"""


@pytest.fixture(autouse=True)
def loud(tmp_path: Path) -> Iterator[None]:
    fake = tmp_path / "docker"
    fake.write_text(f"#!{sys.executable}\n{LOUD}")
    fake.chmod(0o755)
    with patch.dict(os.environ, {"PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"}):
        yield


@pytest.fixture
def _failed_exec() -> Iterator[None]:
    with patch.dict(os.environ, {"FAKE_EXEC_CODE": "3"}):
        yield


def describe_Container_exec() -> None:
    async def it_writes_complete_output_to_files(tmp_path: Path) -> None:
        with (tmp_path / "out").open("wb") as out, (tmp_path / "err").open("wb") as err:
            await Container("box").exec("cat", stdout=out, stderr=err)
        assert (tmp_path / "out").read_bytes() == b"x" * (128 * 65536)
        assert (tmp_path / "err").read_bytes() == b"done\n"

    async def it_raises_with_the_end_of_stderr_on_failure(_failed_exec: None) -> None:
        with pytest.raises(DockerException) as raised:
            await Container("box").exec("cat")
        assert raised.value.return_code == 3
        assert raised.value.stderr == "done\n"
