import dataclasses

import pytest

from botbox.RunResult import RunResult


def describe_run_result() -> None:
    def it_holds_the_exit_code_and_whether_memory_ran_out() -> None:
        assert [f.name for f in dataclasses.fields(RunResult)] == ["exit_code", "oom_killed"]

    def it_leaves_the_oom_kill_unknown_by_default() -> None:
        assert RunResult(0).oom_killed is None

    def it_is_frozen() -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            RunResult(0).exit_code = 1  # type: ignore[misc]

    def it_compares_by_value() -> None:
        assert RunResult(3) == RunResult(3)
        assert RunResult(3) != RunResult(4)
        assert RunResult(3) != RunResult(3, oom_killed=False)
