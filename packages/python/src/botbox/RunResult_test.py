import dataclasses

import pytest

from botbox.RunResult import RunResult


def describe_run_result() -> None:
    def it_keeps_only_the_exit_code() -> None:
        result = RunResult(exit_code=7)
        assert dataclasses.asdict(result) == {"exit_code": 7}

    def it_is_frozen() -> None:
        result = RunResult(exit_code=0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.exit_code = 1  # type: ignore[misc]

    def it_compares_by_value() -> None:
        assert RunResult(exit_code=0) == RunResult(exit_code=0)
