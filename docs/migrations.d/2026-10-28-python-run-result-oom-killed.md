# botbox: `RunResult.oom_killed`

## Summary

`RunResult` has a second field, `oom_killed: bool | None`, defaulting to `None`. A run or session that ends normally sets it to `True` or `False` from Docker's `State.OOMKilled`. A timeout or an interrupted session leaves it `None`.

## Required changes

Code that compares a result to `RunResult(code)` compares `exit_code` instead, or adds `oom_killed=False`. Code that reads `dataclasses.asdict(result)` gets the extra key.

## Deprecations removed

None.

## Behavior changes without code changes

None beyond the new field.

## Verification

Run a command with `Botbox(..., memory="64m")` that allocates past the cap in a child process. Expect `oom_killed` `True`. Without a cap and with no OOM kill, expect `False`.
