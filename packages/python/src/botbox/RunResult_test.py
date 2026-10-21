import dataclasses

import pytest

from botbox.RunResult import RunResult


@pytest.fixture
def result() -> RunResult:
    return RunResult("out", "err", 0, {".claude/projects/p/s.jsonl": "{}"}, "log", "an-image")


def describe_run_result() -> None:
    def it_holds_what_the_run_left_in_order(result: RunResult) -> None:
        assert dataclasses.astuple(result) == (
            "out",
            "err",
            0,
            {".claude/projects/p/s.jsonl": "{}"},
            "log",
            "an-image",
        )

    def it_names_its_fields(result: RunResult) -> None:
        assert [f.name for f in dataclasses.fields(result)] == [
            "stdout",
            "stderr",
            "exit_code",
            "transcript",
            "proxy",
            "image",
        ]

    def it_is_frozen(result: RunResult) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.exit_code = 1  # type: ignore[misc]

    def it_compares_by_value(result: RunResult) -> None:
        assert result == RunResult(
            "out", "err", 0, {".claude/projects/p/s.jsonl": "{}"}, "log", "an-image"
        )
