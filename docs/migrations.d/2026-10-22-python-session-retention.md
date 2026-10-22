# botbox: sessions keep only what they need

## Summary

A session used to keep every byte its agent printed, and returned all of it in `live.result.stdout`. A long pi turn, whose `message_update` events repeat the whole message so far, grew that to gigabytes and ran the host process out of memory. Now a session drops each line once it is read. `live.result.stdout` keeps only the lines that aren't JSON events (stray output, errors), the last 1 MiB of them. A line over 1 GiB ends the session with `botbox.OutputLimitExceeded`.

## Required changes

Read events from `stream()` or `message()`, not from `live.result.stdout`:

```python
# before
async with box.session() as live:
    await live.message(text)
events = [json.loads(line) for line in live.result.stdout.splitlines()]

# after
async with box.session() as live:
    events = await live.message(text)
```

To keep every event of the session, collect them as they arrive. `message()` already returns each turn's events.

## Deprecations removed

None.

## Behavior changes without code changes

- `live.result.stdout` from `session()` holds the non-event lines only, trimmed to their last 1 MiB. `run()` is unchanged.
- A line over 1 GiB on the agent's stdout kills the agent and raises `botbox.OutputLimitExceeded` from the read that hit it, from later reads, and from leaving the block. `live.result` is still set, with `exit_code` -1.
- `live.stdout.into` holds only output not yet read, not the whole stream.

## Verification

```python
async with Botbox(ClaudeAgent()).session() as live:
    events = await live.message("Say hi.")
assert events
assert '"type"' not in live.result.stdout
```

The assert passes: event lines no longer appear in `stdout`.
