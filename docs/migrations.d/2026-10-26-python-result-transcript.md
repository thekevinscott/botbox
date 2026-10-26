# botbox: RunResult has no transcript

## Summary

`RunResult.transcript` is removed. The agent's transcripts are only kept on disk, in the
`output` directory's `transcripts/`, written by the CLI while it runs. botbox reads none of
them back.

## Required changes

Pass `output` and read the files instead of the field:

```python
# before
result = await box.run(command)
transcript = result.transcript

# after
result = await box.run(command, output=output)
files = (output / "transcripts").rglob("*.jsonl")
transcript = {p: p.read_text() for p in files if p.is_file() and not p.is_symlink()}
```

`output/transcripts/` is the agent's sessions directory, such as `~/.claude/projects`, so a
file's path under it drops that prefix from the old keys. Sessions take `output` the same way. `RunResult(...)` built by hand drops its fourth
argument: `RunResult(stdout, stderr, exit_code, proxy, image)`.

## Deprecations removed

None. The field is removed without a deprecation period.

## Behavior changes without code changes

- Without `output`, transcripts are deleted with the temporary home.
- A session no longer warns "could not read its session artifacts" over an unreadable
  transcript directory.

## Verification

```python
import asyncio
from pathlib import Path

from botbox import Botbox, ClaudeAgent

output = Path("/tmp/botbox-check")
result = asyncio.run(Botbox(ClaudeAgent()).run("echo hi", output=output))
print(hasattr(result, "transcript"), (output / "transcripts").is_dir())
```

Expected (unverified): `False True`.
