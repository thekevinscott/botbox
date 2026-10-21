"""The pi image: what a command run in it can use."""

import pytest

from botbox import Botbox, PiAgent, RunResult


@pytest.fixture(scope="module")
def result() -> RunResult:
    box = Botbox(PiAgent("openrouter", api_key="unused"))
    return box.run("python3 -c 'print(6 * 7)'")


def describe_the_pi_image() -> None:
    def it_runs_python(result: RunResult) -> None:
        assert (result.exit_code, result.stdout) == (0, "42\n")
