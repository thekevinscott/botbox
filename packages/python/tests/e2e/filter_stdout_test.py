"""An agent's `filter_stdout` drops lines from a real container run before `stdout.txt`."""

import asyncio
from pathlib import Path

import pytest
from conftest import API_KEY

from botbox import Botbox, ClaudeAgent

MARKER = "botbox-filter-marker"


class Filtering(ClaudeAgent):
    def filter_stdout(self, line: bytes) -> bytes | None:
        return None if MARKER.encode() in line else line


class Raising(ClaudeAgent):
    def filter_stdout(self, line: bytes) -> bytes | None:
        if MARKER.encode() in line:
            raise ValueError(line)
        return line


@pytest.fixture(scope="module")
def output(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("filter-stdout")
    command = f"echo before; echo {MARKER}; echo {MARKER} >&2; head -c 200000 /dev/zero"
    command += " | tr '\\0' x; echo; printf after"
    result = asyncio.run(Botbox(Filtering(api_key=API_KEY)).run(command, output=output))
    assert result.exit_code == 0, (output / "stderr.txt").read_text(errors="replace")
    return output


def describe_an_agent_with_filter_stdout() -> None:
    def it_drops_the_marker_line_and_keeps_the_rest(output: Path) -> None:
        stdout = (output / "stdout.txt").read_text()
        assert stdout == "before\n" + "x" * 200000 + "\nafter"

    def it_leaves_stderr_as_printed(output: Path) -> None:
        assert f"{MARKER}\n" in (output / "stderr.txt").read_text()

    def it_raises_what_the_filter_raises(tmp_path: Path) -> None:
        command = f"echo before; echo {MARKER}; sleep 600"
        with pytest.raises(ValueError, match=MARKER):
            asyncio.run(Botbox(Raising(api_key=API_KEY)).run(command, output=tmp_path))
        assert (tmp_path / "stdout.txt").read_text() == "before\n"
