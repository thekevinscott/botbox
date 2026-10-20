---
diataxis: how-to
---

# Holding a session

Keep one agent process alive across several messages with `session()`. Context carries over between messages, and anything the agent starts in the background keeps running until the session closes.

```python
agent = PiAgent("openrouter", "openai/gpt-4o-mini")

with Botbox(agent) as box:
    with box.session(mounts=[("./work", "/work", "rw")], workdir="/work") as session:
        events = session.message("Start the dev server in the background")
        events = session.message("Now run the tests against it")
    result = session.result
```

`message()` blocks until the agent ends its turn, then returns that turn's events: the CLI's JSON lines, parsed. The events are the CLI's own format; for pi, the reply is the last `message_end` whose `message.role` is `assistant`.

Closing the session ends the CLI's input, waits for it to exit, and returns a [`RunResult`](../reference/#runresult). Leaving the `with` block closes it; `session.result` holds the same `RunResult`.

Only `PiAgent` has a session mode so far. `session()` raises `TypeError` for the others.

Next: [Reading the result](./reading-the-result).
