# botbox: sessions removed

## Summary

Sessions are gone until their API is redesigned. `Botbox.session()` and the `Session` it yielded are removed, along with the agent methods only a session used: `session_command`, `encode` and `turn_ended`. The `MESSAGE_TYPE` enums on `ClaudeAgent` and `PiAgent` go too.

## Required changes

Code that held a session runs each turn with `run()` instead. `run()` takes a shell command, so build it with the agent's `command`, and read the reply from `stdout.txt` in `output`:

```python
# Before
async with box.session(output=out) as live:
    reply = await live.message("hi")

# After
result = await box.run(box.agent.command("hi"), output=out)
reply = (Path(out) / "stdout.txt").read_text()
```

A subclass that overrode `session_command`, `encode` or `turn_ended` drops the override. One that appended flags to `session_command` appends them to `command` instead. Code that read `ClaudeAgent.MESSAGE_TYPE` or `PiAgent.MESSAGE_TYPE` compares against the string values directly.

## Deprecations removed

None.

## Behavior changes without code changes

None. `run()` behaves as before.

## Verification

`python -c "import botbox; print(hasattr(botbox, 'Session'), hasattr(botbox.Botbox, 'session'))"` prints `False False`.
