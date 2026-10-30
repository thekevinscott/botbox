# Sessions yield the agent

## Summary

`session()` yields the agent, which sends and reads messages, instead of a `Session` that ran one turn at a time. Turns are gone: an agent answers with as many messages as it likes, and long-running agents talking to each other don't wait for a turn to end.

## Required changes

```python
# before
async with box.session() as live:
    events = await live.message("Fix the test.")
    async for event in live.stream("Run the suite."):
        print(event["type"])
print(live.result)

# after
async with box.session() as agent:
    replies = agent.replies
    await agent.send("Fix the test.")
    print((await anext(replies)).text)
    messages = agent.messages
    await agent.send("Run the suite.")
    async for message in messages:
        print(message.type, message.event)
        if message.type == agent.MESSAGE_TYPE.ASSISTANT and message.text:
            break
print(box.result)
```

- `botbox.Session` is gone. Type a session as the agent.
- A session's `RunResult` is in `box.result`, not on what the block yields.
- `Agent.parse_event(line)` is gone. A custom agent overrides `read_message(line) -> Message | None` and sets `MESSAGE_TYPE`, a `StrEnum` with an `ASSISTANT` member.
- Events that aren't messages, such as Claude's `result` or pi's `agent_settled`, are no longer yielded. Read them from `output/stdout.txt`.

## Deprecations removed

None.

## Behavior changes without code changes

- Open `replies` or `messages` before `send`: an iterator starts when it is read, and misses what came before.

## Verification

```python
import botbox
assert not hasattr(botbox, "Session")
assert hasattr(botbox, "Message")
```
