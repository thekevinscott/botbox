"""What a real run leaves behind on the host: only its output, pass or fail, with nothing lost."""

import asyncio
import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from run_test import Marking, Runs

from botbox import Botbox


@pytest.fixture(scope="module")
def box() -> Botbox:
    box = Botbox(Marking())
    asyncio.run(box.build())
    return box


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


@pytest.fixture
def output(tmp_path: Path) -> Path:
    return tmp_path / "output"


def describe_teardown() -> None:
    @pytest.mark.parametrize("command", ["true", "exit 1", "kill -9 $$"])
    async def it_leaves_nothing(box: Botbox, runs: Runs, output: Path, command: str) -> None:
        await box.run(command, output=output)
        assert len(runs.tokens) == 1
        assert runs.leftovers() == []

    async def it_leaves_nothing_after_an_async_with_block(
        box: Botbox, runs: Runs, output: Path
    ) -> None:
        async with box:
            await box.run("true", output=output / "first")
            await box.run("exit 1", output=output / "second")
        assert len(runs.tokens) == 2
        assert runs.leftovers() == []


def describe_a_command_that_ends_at_once() -> None:
    @pytest.mark.parametrize("attempt", range(5))
    async def it_still_returns_its_exit_code_and_output(
        box: Botbox,
        output: Path,
        attempt: int,  # noqa: ARG001
    ) -> None:
        result = await box.run("echo out; echo err >&2; exit 5", output=output)
        stdout, stderr = (output / "stdout.txt").read_text(), (output / "stderr.txt").read_text()
        assert (stdout, stderr, result.exit_code) == ("out\n", "err\n", 5)

    async def it_still_keeps_all_of_a_large_output(box: Botbox, output: Path) -> None:
        result = await box.run("seq 1 200000; seq 1 100000 >&2; exit 7", output=output)
        stdout, stderr = (output / "stdout.txt").read_text(), (output / "stderr.txt").read_text()
        assert stdout.splitlines() == [str(n) for n in range(1, 200001)]
        assert stderr.splitlines() == [str(n) for n in range(1, 100001)]
        assert result.exit_code == 7
