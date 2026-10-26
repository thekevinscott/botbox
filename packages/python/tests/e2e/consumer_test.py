"""The README's sample consumer Dockerfile, built as a `dockerfile` layer and run.

The Dockerfile is read out of the root README at test time, so the test follows the README.
It is written to a stable path: the layer's tag is derived from the Dockerfile's path.
"""

import asyncio
import re
from pathlib import Path

import pytest

from botbox import Botbox, ClaudeAgent, RunResult

README = Path(__file__).parents[4] / "README.md"


def sample_dockerfile() -> str:
    section = README.read_text().split("## Sample consumer Dockerfile extension", 1)[1]
    match = re.search(r"```dockerfile\n(.*?)```", section, re.DOTALL)
    assert match, "no dockerfile block in the README's sample consumer section"
    return match.group(1)


@pytest.fixture(scope="module")
def output(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("consumer")


@pytest.fixture(scope="module")
def result(pytestconfig: pytest.Config, output: Path) -> RunResult:
    dockerfile = pytestconfig.cache.mkdir("consumer") / "Dockerfile"
    dockerfile.write_text(sample_dockerfile())
    box = Botbox(ClaudeAgent(), dockerfile=dockerfile)
    command = "uv --version && pytest --version && vitest --version"
    return asyncio.run(box.run(command, output=output))


def describe_the_sample_consumer_dockerfile() -> None:
    def it_puts_its_tools_on_the_path(result: RunResult, output: Path) -> None:
        assert result.exit_code == 0, (output / "stderr.txt").read_text()

    def it_runs_the_pinned_versions(result: RunResult, output: Path) -> None:
        assert result
        stdout = (output / "stdout.txt").read_text()
        assert "uv 0.12.10" in stdout
        assert "pytest 9.1.1" in stdout + (output / "stderr.txt").read_text()
        assert "vitest/2.1.3" in stdout
