# botbox: `run()` requires `output`

## Summary

`Botbox.run()` takes a required keyword `output`. The route that captured stdout and stderr
in Python when `output` was omitted, and kept the proxy log in the temp home, is gone. Every
run writes `stdout.txt`, `stderr.txt`, `proxy.log` and `transcripts/` into `output`, as passing
`output` already did.

## Required changes

Pass a directory to every run:

```python
# before
result = await box.run("echo hi")

# after
result = await box.run("echo hi", output="runs/hi")
```

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
