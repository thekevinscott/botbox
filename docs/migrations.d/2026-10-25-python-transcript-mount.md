# botbox: agents name a sessions directory, and output holds transcripts

## Summary

An `Agent` declares `sessions_dir`, the directory under its home where the CLI writes
`.jsonl` session transcripts, in place of the `transcripts` glob. With `run(output=...)`,
botbox mounts `output/transcripts/` over that directory, so transcripts are written to disk
as the agent runs and are not read back into the result.

## Required changes

A custom `Agent` replaces its glob with the directory it matched under:

```python
# before
class MyAgent:
    transcripts = ".my-cli/sessions/**/*.jsonl"

# after
class MyAgent:
    sessions_dir = ".my-cli/sessions"
```

Every `.jsonl` file at any depth under `sessions_dir` counts as transcript. Callers that
pass `output` and read `result.transcript` read `output / "transcripts"` instead:

```python
# before
result = await box.run(command, output=output)
transcript = result.transcript

# after
await box.run(command, output=output)
transcript = {p: p.read_text() for p in (output / "transcripts").rglob("*.jsonl")}
```

The built-in agents need no change.

## Deprecations removed

None. `Agent.transcripts` is removed without a deprecation period.

## Behavior changes without code changes

- With `output`, `result.transcript` is `{}`, including in `Timeout.result`.
- With `output`, existing files in `output/transcripts/` are kept; a reused folder
  accumulates sessions.
- `sessions_dir` is created in the temp home after credentials are staged, with or without
  `output`.
- Without `output`, `result.transcript` keys and contents are unchanged.

## Verification

```python
import asyncio
from pathlib import Path

from botbox import Botbox, ClaudeAgent

output = Path("/tmp/botbox-check")
agent = ClaudeAgent()
result = asyncio.run(Botbox(agent).run(agent.command("Say hi"), output=output))
print(result.transcript, sorted(p.suffix for p in (output / "transcripts").rglob("*.jsonl")))
print(sorted(p.name for p in output.rglob("*credentials*")))
```

Expected: `{} ['.jsonl']`, then `[]`.
