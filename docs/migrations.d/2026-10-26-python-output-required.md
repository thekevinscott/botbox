# botbox: `output` is required

## Summary

`Botbox.run()` and `Botbox.session()` take a required keyword `output`. The route that
captured stdout and stderr in Python when `output` was omitted is gone.
Every run and session writes `stdout.txt`, `stderr.txt`, `proxy.log` and `transcripts/` into
`output`, as passing `output` already did.

## Required changes

Pass a directory to every call:

```python
# before
result = await box.run("echo hi")
async with box.session() as live: ...

# after
result = await box.run("echo hi", output="runs/hi")
async with box.session(output="runs/chat") as live: ...
```

Code that read `live.stdout` or `live.stderr` on a `Session` reads `output / "stdout.txt"`
and `output / "stderr.txt"` instead. Code that builds a `Session` itself passes
`Session(agent, stdin, client, readline)`, where `readline` is an async callable returning the
next line, or `b""` at the end.

## Deprecations removed

None. Omitting `output` stops working without a deprecation period.

## Behavior changes without code changes

- Callers that already passed `output` see no change.

## Verification

```python
import asyncio
from pathlib import Path

from botbox import Botbox, ClaudeAgent

box = Botbox(ClaudeAgent())
try:
    asyncio.run(box.run("echo hi"))
except TypeError as error:
    print(error)
output = Path("/tmp/botbox-check")
print(asyncio.run(box.run("echo hi", output=output)).exit_code, (output / "stdout.txt").read_text())
```

Expected: a `TypeError` naming the missing `output` argument, then `0 hi`.
