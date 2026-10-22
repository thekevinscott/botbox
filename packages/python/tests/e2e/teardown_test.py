"""What a real run leaves behind on the host: nothing, pass or fail, and nothing it said is lost."""

import pytest
from conftest import leftovers

from botbox import Botbox


def describe_teardown() -> None:
    @pytest.mark.parametrize("command", ["true", "exit 1", "kill -9 $$"])
    async def it_leaves_nothing(box: Botbox, command: str) -> None:
        before = leftovers()
        await box.run(command)
        assert leftovers() == before

    async def it_leaves_nothing_after_an_async_with_block(box: Botbox) -> None:
        before = leftovers()
        async with box:
            await box.run("true")
            await box.run("exit 1")
        assert leftovers() == before


def describe_a_command_that_ends_at_once() -> None:
    @pytest.mark.parametrize("attempt", range(5))
    async def it_still_returns_its_exit_code_and_output(
        box: Botbox,
        attempt: int,  # noqa: ARG001
    ) -> None:
        result = await box.run("echo out; echo err >&2; exit 5")
        assert (result.stdout, result.stderr, result.exit_code) == ("out\n", "err\n", 5)

    async def it_still_returns_all_of_a_large_output(box: Botbox) -> None:
        result = await box.run("seq 1 200000; seq 1 100000 >&2; exit 7")
        assert result.stdout.splitlines() == [str(n) for n in range(1, 200001)]
        assert result.stderr.splitlines() == [str(n) for n in range(1, 100001)]
        assert result.exit_code == 7
