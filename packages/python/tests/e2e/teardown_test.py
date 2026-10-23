"""What a real run leaves behind on the host: nothing, pass or fail, and nothing it said is lost."""

import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from run_test import Runs

from botbox import Botbox


@pytest.fixture
def temp(tmp_path: Path) -> Iterator[Path]:
    """This test's own temp dir, so other botbox runs on the host are not counted."""
    directory = tmp_path / "tmp"
    directory.mkdir()
    with patch.object(tempfile, "tempdir", str(directory)):
        yield directory


@pytest.fixture
def runs(temp: Path) -> Iterator[Runs]:
    runs = Runs(temp)
    yield runs
    runs.clean()


def describe_teardown() -> None:
    @pytest.mark.parametrize("command", ["true", "exit 1", "kill -9 $$"])
    async def it_leaves_nothing(output: Path, box: Botbox, runs: Runs, command: str) -> None:
        await box.run(command, output=output)
        assert len(runs.tokens) == 1
        assert runs.leftovers() == []

    async def it_leaves_nothing_after_an_async_with_block(
        output: Path, box: Botbox, runs: Runs
    ) -> None:
        async with box:
            await box.run("true", output=output)
            await box.run("exit 1", output=output)
        assert len(runs.tokens) == 2
        assert runs.leftovers() == []


def describe_a_command_that_ends_at_once() -> None:
    @pytest.mark.parametrize("attempt", range(5))
    async def it_still_returns_its_exit_code_and_output(
        output: Path,
        box: Botbox,
        attempt: int,  # noqa: ARG001
    ) -> None:
        result = await box.run("echo out; echo err >&2; exit 5", output=output)
        assert (
            (output / "stdout.txt").read_text(errors="replace"),
            (output / "stderr.txt").read_text(errors="replace"),
            result.exit_code,
        ) == ("out\n", "err\n", 5)

    async def it_still_returns_all_of_a_large_output(output: Path, box: Botbox) -> None:
        result = await box.run("seq 1 200000; seq 1 100000 >&2; exit 7", output=output)
        assert (output / "stdout.txt").read_text(errors="replace").splitlines() == [
            str(n) for n in range(1, 200001)
        ]
        assert (output / "stderr.txt").read_text(errors="replace").splitlines() == [
            str(n) for n in range(1, 100001)
        ]
        assert result.exit_code == 7
