# `session()`

```python
async with box.session(
    *,
    mounts: Sequence[tuple[str | Path, str | Path, Literal["ro", "rw"]]] = (),
    workdir: str | Path | None = None,
    timeout: float | None = None,
    output: str | Path | None = None,
) as live: ...
```

Starts the agent's CLI in its session mode and holds it open, yielding the agent. `mounts`, `workdir` and `timeout` are as for [`run()`](./run), and so are the lockdown, labels and temp directory. Background processes the agent starts live until the session ends. Leaving the block ends the CLI's input, waits for it to exit and removes the session's containers and temp directory. Then the [`RunResult`](./run-result) is in `box.result`. With `output`, `stdout.txt` holds every line the CLI wrote.

- `output` is as for [`run()`](./run): the CLI's stdout and stderr go to `stdout.txt` and `stderr.txt`, the proxy's output to `proxy.log`, and the transcripts to `transcripts/`. A failing `output` doesn't stop the messages. Read the files for what the session left. A Docker error carries the last 64 KiB of stderr. Omit `output` and the streams, transcripts and proxy log are deleted after the session.
- `timeout` covers the whole block and the wait for the CLI to exit. When it runs out, the session tears down as a cancel does and raises [`botbox.Timeout`](./botbox#timeout), whose `result` is `box.result`.
- Cancelling the task, or an `asyncio.timeout` firing, kills the CLI and tears the session down, even through a second cancel. So does an exception out of the block. `box.result` has `exit_code` -1, and what was written so far stays in `output`.
- A Docker client that dies while the daemon is up, or a container that never started, raises `DockerException` when the block ends, as `run()` does.
- Raises `NotImplementedError` for an agent with no session mode, such as `CodexAgent`, before anything is built.

```python
box = Botbox(ClaudeAgent())
async with box.session() as agent:
    replies = agent.replies
    await agent.send("Fix the failing test.")
    print((await anext(replies)).text)
print(box.result.exit_code)
```

## The agent in a session

```python
await agent.send(text: str)
agent.replies -> AsyncIterator[Message]
agent.messages -> AsyncIterator[Message]
agent.on(kind: Literal["reply", "message"], callback: Callable[[Message], object])
```

`await agent.send(text)` writes `text` to the CLI in its harness's input format and returns. It doesn't wait for an answer.

`agent.messages` yields each message the CLI prints, as it prints it. `agent.replies` yields only the agent's own messages that have text; an agent's message that is only a tool call has none, and is left out. Each read of either returns a new iterator, which starts at that moment and ends when the CLI's stdout does. So open one before `send`, or a quick answer may come before it. Any number can be open at once, and each gets every message. An open iterator holds the messages it hasn't yielded yet. `async for` over one runs until the CLI exits, so break out of it when you have what you need.

`agent.on("reply", fn)` and `agent.on("message", fn)` call `fn` with each reply or message, as it is read, until the session ends. A callback that raises ends the session, and its exception comes out of the block.

`agent.send`, `agent.replies`, `agent.messages` and `agent.on` raise `RuntimeError` outside a session.

Messages come from inside the box, and any process there can forge one. See [Forged session messages](../threat-model#forged-session-messages).

## `Message`

```python
message.type -> str
message.text -> str
message.event -> dict[str, Any]
```

`type` is the harness's name for who sent it, one of the agent's `MESSAGE_TYPE`, such as `agent.MESSAGE_TYPE.ASSISTANT`. `text` is the message's text parts joined, empty when it has none. `event` is the JSON object the CLI printed, unchanged.

| Agent        | `MESSAGE_TYPE`                                                                                         | Read from                                     |
| ------------ | ------------------------------------------------------------------------------------------------------ | --------------------------------------------- |
| `ClaudeAgent` | `ASSISTANT`, `USER`                                                                                    | `assistant` and `user` events                 |
| `PiAgent`    | `ASSISTANT`, `USER`, `TOOL_RESULT`, `SYSTEM`, `BASH_EXECUTION`, `CUSTOM`, `BRANCH_SUMMARY`, `COMPACTION_SUMMARY` | `message_end` events, by `message.role` |

Other lines on stdout, such as Claude's `result` or pi's `agent_settled`, are not messages. They stay in `stdout.txt` with `output`.
