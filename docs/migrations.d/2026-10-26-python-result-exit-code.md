# botbox: RunResult holds only the exit code

## Summary

`RunResult` is now `RunResult(exit_code)`. What a run or session left is on disk in its
`output` directory, written while it runs. botbox reads none of it back.

## Required changes

Pass `output` and read the files instead of the result fields:

```python
# before
result = await box.run(command)
print(result.stdout, result.stderr, result.image)

# after
result = await box.run(command, output=output)
print((output / "stdout.txt").read_text(), (output / "stderr.txt").read_text())
image = await box.build()
```

Sessions take `output` the same way; `live.result` and `Timeout.result` hold only
`exit_code`. The image tag that ran is the return value of `await box.build()`.

`RunResult(...)` built by hand takes one argument: `RunResult(0)`.

## Deprecations removed

None. The fields are removed without a deprecation period.

## Behavior changes without code changes

- `RunResult` no longer carries the streams. Without `output`, `run()` drops them when it returns.
- The "could not read its session artifacts" warning is gone.
- Without `output`, a session still buffers its streams in memory. `live.stdout` and `live.stderr` are unchanged and outlive the block.

## Verification

```python
import asyncio
from pathlib import Path

from botbox import Botbox, ClaudeAgent

output = Path("/tmp/botbox-check")
result = asyncio.run(Botbox(ClaudeAgent()).run("echo hi", output=output))
print(result, (output / "stdout.txt").read_text())
```

Expected (unverified): `RunResult(exit_code=0) hi`.
