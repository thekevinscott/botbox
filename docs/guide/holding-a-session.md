# Holding a session

Keep one agent process alive across several messages with `session()`. Context carries over between messages, and anything the agent starts in the background keeps running until the session closes.

```python
agent = PiAgent("openrouter", "openai/gpt-4o-mini")

async with Botbox(agent) as box:
    async with box.session(
        mounts=[("./work", "/work", "rw")], workdir="/work", output="runs/session"
    ) as live:
        replies = live.replies
        await live.send("Start the dev server in the background")
        print((await anext(replies)).text)
        await live.send("Now run the tests against it")
        print((await anext(replies)).text)
    result = box.result
```

`session()` yields the agent. `await live.send(text)` sends a message and returns without waiting. `live.replies` yields the agent's messages that have text, as they arrive. An agent may say several things in answer to one message, so read until you have what you need. `live.messages` yields every message, the agent's tool calls and their results included. Each [`Message`](../api/session#message) has a `type`, its `text` and the CLI's raw `event`.

Each read of `live.replies` or `live.messages` starts a new iterator from that moment, so open it before you send. Both end when the CLI exits. To be called instead, pass a function to `live.on("reply", fn)` or `live.on("message", fn)`.

Two agents can talk by passing replies along:

```python
async with Botbox(alice).session() as a, Botbox(bob).session() as b:
    from_a, from_b = a.replies, b.replies
    await a.send("Propose a plan.")
    await b.send((await anext(from_a)).text)
    print((await anext(from_b)).text)
```

Leaving the `async with` block ends the CLI's input, waits for it to exit and tears the session down. Then `box.result` holds the [`RunResult`](../api/run-result), and the CLI's streams, transcripts and proxy log are in `output`. If the block raises or is cancelled, `box.result` has `exit_code` -1 and `output` keeps what was written.

`ClaudeAgent` and `PiAgent` have a session mode. `CodexAgent` does not: to hold a session with a Codex model, run it through pi on OpenRouter, `PiAgent("openrouter", "openai/<model>")`.

Next: [Reading the result](./reading-the-result).
