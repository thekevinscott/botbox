"""The README's sample consumer Dockerfile, built as a `dockerfile` layer and run.

The Dockerfile is read out of the root README at test time, so the test follows the README.
It is written to a stable path: the layer's tag is derived from the Dockerfile's path.
"""

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
def result(pytestconfig: pytest.Config) -> RunResult:
    dockerfile = pytestconfig.cache.mkdir("consumer") / "Dockerfile"
    dockerfile.write_text(sample_dockerfile())
    box = Botbox(ClaudeAgent(), dockerfile=dockerfile)
    return box.run("uv --version && pytest --version && vitest --version")


def describe_the_sample_consumer_dockerfile() -> None:
    def it_puts_its_tools_on_the_path(result: RunResult) -> None:
        assert result.exit_code == 0, result.stdout + result.stderr

    def it_runs_the_pinned_versions(result: RunResult) -> None:
        assert "uv 0.12.10" in result.stdout
        assert "pytest 9.1.1" in result.stdout + result.stderr
        assert "vitest/2.1.3" in result.stdout
