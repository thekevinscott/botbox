import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from botbox.Session import Session, read_transcript


class Stdin(io.StringIO):
    """Keeps what was written after it's closed, and records each flush."""

    def __init__(self) -> None:
        super().__init__()
        self.written = ""
        self.flushed: list[str] = []

    def write(self, text: str) -> int:
        self.written += text
        return len(text)

    def flush(self) -> None:
        self.flushed.append(self.written)


class BrokenStdin(Stdin):
    """Raises on the first close, the way a pipe to an exited process does."""

    def close(self) -> None:
        if not self.closed:
            super().close()
            raise BrokenPipeError


def lines(*events: Any) -> str:
    return "".join((e if isinstance(e, str) else json.dumps(e)) + "\n" for e in events)


@pytest.fixture
def agent() -> Mock:
    return Mock(
        transcripts="sessions/*.jsonl",
        encode=lambda message: f"<{message}>",
        turn_ended=lambda event: event.get("type") == "end",
    )


def process(stdout: str = "", stderr: str = "", exit_code: int = 0) -> Mock:
    return Mock(
        stdin=Stdin(),
        stdout=io.StringIO(stdout),
        stderr=io.StringIO(stderr),
        wait=Mock(return_value=exit_code),
    )


@pytest.fixture(autouse=True)
def run_result() -> Iterator[MagicMock]:
    with patch("botbox.Session.RunResult", autospec=True) as m:
        yield m


@pytest.fixture
def finish() -> Mock:
    return Mock(return_value=({"sessions/a.jsonl": "{}"}, "a proxy log"))


def session_of(agent: Mock, proc: Mock, finish: Mock) -> Session:
    return Session(agent, proc, "a-container", "an-image:latest", finish)


def describe_message() -> None:
    def it_writes_the_encoded_message_as_one_line(agent: Mock, finish: Mock) -> None:
        proc = process(lines({"type": "end"}))
        session_of(agent, proc, finish).message("hi")
        assert proc.stdin.written == "<hi>\n"

    def it_flushes_the_line_before_reading(agent: Mock, finish: Mock) -> None:
        proc = process(lines({"type": "end"}))
        session_of(agent, proc, finish).message("hi")
        assert proc.stdin.flushed == ["<hi>\n"]

    def it_returns_the_turns_events_through_the_last(agent: Mock, finish: Mock) -> None:
        proc = process(lines({"type": "start"}, {"type": "end"}, {"type": "next"}))
        assert session_of(agent, proc, finish).message("hi") == [{"type": "start"}, {"type": "end"}]

    def it_leaves_the_next_turns_events_for_the_next_message(agent: Mock, finish: Mock) -> None:
        proc = process(lines({"type": "end", "n": 1}, {"type": "end", "n": 2}))
        session = session_of(agent, proc, finish)
        session.message("one")
        assert session.message("two") == [{"type": "end", "n": 2}]

    def it_skips_lines_that_are_not_json_objects(agent: Mock, finish: Mock) -> None:
        proc = process(lines("not json", [1, 2], {"type": "end"}))
        assert session_of(agent, proc, finish).message("hi") == [{"type": "end"}]

    def it_returns_what_arrived_when_the_cli_exits_mid_turn(agent: Mock, finish: Mock) -> None:
        proc = process(lines({"type": "start"}))
        assert session_of(agent, proc, finish).message("hi") == [{"type": "start"}]


def describe_close() -> None:
    def it_ends_the_clis_input(agent: Mock, finish: Mock) -> None:
        proc = process()
        session_of(agent, proc, finish).close()
        assert proc.stdin.closed

    def it_returns_what_the_session_left(agent: Mock, finish: Mock, run_result: MagicMock) -> None:
        proc = process(lines({"type": "end"}, "trailing"), stderr="a warning\n", exit_code=3)
        session = session_of(agent, proc, finish)
        session.message("hi")
        assert session.close() is run_result.return_value
        run_result.assert_called_once_with(
            lines({"type": "end"}, "trailing"),
            "a warning\n",
            3,
            {"sessions/a.jsonl": "{}"},
            "a proxy log",
            "a-container",
            "an-image:latest",
        )

    def it_keeps_the_lines_that_were_not_events_in_stdout(
        agent: Mock, finish: Mock, run_result: MagicMock
    ) -> None:
        proc = process(lines("noise", {"type": "end"}))
        session = session_of(agent, proc, finish)
        session.message("hi")
        session.close()
        assert run_result.call_args.args[0] == lines("noise", {"type": "end"})

    def it_keeps_the_result(agent: Mock, finish: Mock) -> None:
        session = session_of(agent, process(), finish)
        assert session.result is None
        assert session.close() is session.result

    def it_tears_down_once(agent: Mock, finish: Mock) -> None:
        session = session_of(agent, process(), finish)
        first = session.close()
        assert session.close() is first
        finish.assert_called_once_with()

    def it_tolerates_a_cli_that_already_exited(
        agent: Mock, finish: Mock, run_result: MagicMock
    ) -> None:
        proc = process(exit_code=1)
        proc.stdin = BrokenStdin()
        session_of(agent, proc, finish).close()
        assert run_result.call_args.args[2] == 1


def describe_with() -> None:
    def it_is_the_session(agent: Mock, finish: Mock) -> None:
        session = session_of(agent, process(), finish)
        with session as entered:
            assert entered is session

    def it_closes_on_exit(agent: Mock, finish: Mock) -> None:
        with session_of(agent, process(), finish) as session:
            pass
        assert session.result is not None

    def it_closes_when_the_block_raises(agent: Mock, finish: Mock) -> None:
        session = session_of(agent, process(), finish)
        with pytest.raises(RuntimeError), session:
            raise RuntimeError
        finish.assert_called_once_with()


def describe_read_transcript() -> None:
    def it_reads_matching_files_by_path_relative_to_the_home(tmp_path: Path) -> None:
        (tmp_path / "sessions").mkdir()
        (tmp_path / "sessions" / "b.jsonl").write_text("b")
        (tmp_path / "sessions" / "a.jsonl").write_text("a")
        (tmp_path / "sessions" / "notes.txt").write_text("x")
        assert read_transcript(tmp_path, "sessions/*.jsonl") == {
            "sessions/a.jsonl": "a",
            "sessions/b.jsonl": "b",
        }

    def it_skips_directories_that_match(tmp_path: Path) -> None:
        (tmp_path / "sessions" / "dir.jsonl").mkdir(parents=True)
        assert read_transcript(tmp_path, "sessions/*.jsonl") == {}
