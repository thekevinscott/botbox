"""A plain shell command through a real run: no agent, nothing billed.

It still goes through everything `run()` sets up: the image, the temp home, the network and
the proxy sidecar.
"""

import pytest

from botbox import Botbox, RunResult


@pytest.fixture(scope="module")
def result(box: Botbox) -> RunResult:
    return box.run("echo hi; echo err >&2; exit 3")


def describe_a_shell_command() -> None:
    def it_returns_a_run_result(result: RunResult) -> None:
        assert isinstance(result, RunResult)

    def it_returns_stdout(result: RunResult) -> None:
        assert result.stdout == "hi\n"

    def it_returns_stderr(result: RunResult) -> None:
        assert result.stderr == "err\n"

    def it_returns_a_non_zero_exit_as_a_result(result: RunResult) -> None:
        assert result.exit_code == 3

    def it_returns_the_proxy_log(result: RunResult) -> None:
        """The sidecar ran and its log made it back, even with no connection to log."""
        assert "Starting main loop" in result.proxy

    def it_returns_no_transcript_when_no_agent_ran(result: RunResult) -> None:
        assert result.transcript == {}

    def it_names_the_image_that_ran(box: Botbox, result: RunResult) -> None:
        assert result.image == box.build()
