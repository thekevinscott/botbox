# botbox: `session()` requires `output`

## Summary

`Botbox.session()` takes a required keyword `output`. The route that captured the CLI's
stdout and stderr in Python when `output` was omitted is gone. Every session writes
`stdout.txt`, `stderr.txt`, `proxy.log` and `transcripts/` into `output`, as passing `output`
already did.

## Required changes

Pass a directory to every session:

```python
# before
async with box.session() as live: ...

# after
async with box.session(output="runs/chat") as live: ...
```

Read what the session left from `output / "stdout.txt"` and `output / "stderr.txt"`.

## Deprecations removed

None. Omitting `output` stops working without a deprecation period.

## Behavior changes without code changes

- Callers that already passed `output` see no change.

## Verification

```python
import asyncio

from botbox import Botbox, ClaudeAgent


async def main() -> None:
    try:
        async with Botbox(ClaudeAgent()).session():
            pass
    except TypeError as error:
        print(error)


asyncio.run(main())
```

Expected: a `TypeError` naming the missing `output` argument.
