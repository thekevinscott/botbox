# botbox: `Session` drops `stdout` and `stderr`

## Summary

A session's streams only go to files in its `output`, so `Session` no longer holds them.

## Required changes

Code that read `live.stdout` or `live.stderr` reads `output / "stdout.txt"` and
`output / "stderr.txt"` instead. Code that builds a `Session` itself passes
`Session(agent, stdin, client, readline)`, where `readline` is an async callable returning the
next line, or `b""` at the end.

## Deprecations removed

None.

## Behavior changes without code changes

- None. `stream()`, `message()` and `result` are unchanged.

## Verification

```python
import inspect

from botbox import Session

print(list(inspect.signature(Session).parameters))
```

Expected: `['agent', 'stdin', 'client', 'readline']`.
