# botbox: a session's `RunResult` is `box.result`

## Summary

A session's `RunResult` moved from the `Session` to the `Botbox` that ran it.

## Required changes

```python
# before
async with box.session() as live:
    await live.message("Fix the test.")
print(live.result.exit_code)

# after
async with box.session() as live:
    await live.message("Fix the test.")
print(box.result.exit_code)
```

## Deprecations removed

None.

## Behavior changes without code changes

None.

## Verification

```python
import botbox
assert not hasattr(botbox.Session, "result")
```
