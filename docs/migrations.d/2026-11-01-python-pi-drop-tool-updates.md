## Summary

The pi image drops repeated `tool_execution_update` snapshots from stdout to limit output size.

## Required changes

Code reading partial tool output from `tool_execution_update` should read the final result from `tool_execution_end`. There is no replacement for intermediate snapshots.

## Deprecations removed

None.

## Behavior changes without code changes

`stdout.txt` no longer contains `tool_execution_update` events when pi runs through the image's `pi` command. Other pi events and stderr remain, and the command's exit code is preserved.

## Verification

From `packages/python`, run `uv run --env-file ../../.env pytest tests/e2e/pi_stdout_filter_test.py`. Expect `2 passed`: the test confirms an unfiltered pi run emits updates, the wrapped pi run omits them, and a failing pi command keeps its exit code.
