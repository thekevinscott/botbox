# botbox: RunResult has no proxy log

## Summary

`RunResult.proxy` is removed. The proxy log is only kept on disk, as `proxy.log` in the
`output` directory, written while the run goes. botbox reads none of it back.

## Required changes

Pass `output` and read the file instead of the field:

```python
# before
result = await box.run(command)
log = result.proxy

# after
result = await box.run(command, output=output)
log = (output / "proxy.log").read_text(errors="replace")
```

Sessions take `output` the same way. `RunResult(...)` built by hand drops its `proxy`
argument: `RunResult(stdout, stderr, exit_code, image)`.

## Deprecations removed

None. The field is removed without a deprecation period.

## Behavior changes without code changes

- Without `output`, the proxy log is deleted with the temporary home.
- The "could not read its proxy log" warning is gone.

## Verification

```python
import asyncio
from pathlib import Path

from botbox import Botbox, ClaudeAgent

output = Path("/tmp/botbox-check")
result = asyncio.run(Botbox(ClaudeAgent()).run("true", output=output))
print(hasattr(result, "proxy"), "Starting main loop" in (output / "proxy.log").read_text())
```

Expected (unverified): `False True`.
