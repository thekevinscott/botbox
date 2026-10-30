# Holding a session

Keep one agent process alive across several messages with `session()`. Context carries over between messages, and anything the agent starts in the background keeps running until the session closes.

```python
agent = PiAgent("openrouter", "openai/gpt-4o-mini")

async with Botbox(agent) as box:
    async with box.session(
        mounts=[("./work", "/work", "rw")], workdir="/work", output="runs/session"
    ) as live:
        events = await live.message("Start the dev server in the background")
        async for event in live.stream("Now run the tests against it"):
            print(event["type"])
    result = box.result
```

`await live.message(text)` returns when the agent ends its turn, with that turn's events: the CLI's JSON lines, parsed. `live.stream(text)` yields the same events as they arrive. The events are the CLI's own format; for pi, the reply is the last `message_end` whose `message.role` is `assistant`.

Leaving the `async with` block ends the CLI's input, waits for it to exit and tears the session down. Then `box.result` holds the [`RunResult`](../api/run-result), and the CLI's streams, transcripts and proxy log are in `output`. If the block raises or is cancelled, `box.result` has `exit_code` -1 and `output` keeps what was written.

`ClaudeAgent` and `PiAgent` have a session mode. `CodexAgent` does not: to hold a session with a Codex model, run it through pi on OpenRouter, `PiAgent("openrouter", "openai/<model>")`.

Next: [Reading the result](./reading-the-result).
