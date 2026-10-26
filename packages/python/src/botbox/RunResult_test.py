import dataclasses

import pytest

from botbox.RunResult import RunResult


def describe_run_result() -> None:
    def it_holds_only_the_exit_code() -> None:
        assert [f.name for f in dataclasses.fields(RunResult)] == ["exit_code"]

    def it_is_frozen() -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            RunResult(0).exit_code = 1  # type: ignore[misc]

    def it_compares_by_value() -> None:
        assert RunResult(3) == RunResult(3)
        assert RunResult(3) != RunResult(4)
