"""What a real run leaves behind on the host: nothing, pass or fail, and nothing it said is lost."""

import pytest
from conftest import leftovers

from botbox import Botbox


def describe_teardown() -> None:
    @pytest.mark.parametrize("command", ["true", "exit 1", "kill -9 $$"])
    def it_leaves_nothing(box: Botbox, command: str) -> None:
        before = leftovers()
        box.run(command)
        assert leftovers() == before

    def it_leaves_nothing_after_a_with_block(box: Botbox) -> None:
        before = leftovers()
        with box:
            box.run("true")
            box.run("exit 1")
        assert leftovers() == before


def describe_a_container_that_removes_itself_on_exit() -> None:
    @pytest.mark.parametrize("attempt", range(5))
    def it_still_returns_the_exit_code_of_a_command_that_ends_at_once(
        box: Botbox,
        attempt: int,  # noqa: ARG001
    ) -> None:
        result = box.run("echo out; echo err >&2; exit 5")
        assert (result.stdout, result.stderr, result.exit_code) == ("out\n", "err\n", 5)

    def it_still_returns_all_of_a_large_output(box: Botbox) -> None:
        result = box.run("seq 1 200000; seq 1 100000 >&2; exit 7")
        assert result.stdout.splitlines() == [str(n) for n in range(1, 200001)]
        assert result.stderr.splitlines() == [str(n) for n in range(1, 100001)]
        assert result.exit_code == 7
