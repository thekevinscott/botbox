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

Starts the agent's CLI in its session mode and holds it open, yielding a [`Session`](#session). `mounts`, `workdir` and `timeout` are as for [`run()`](./run), and so are the lockdown, labels and temp home. Background processes the agent starts live until the session ends. Leaving the block ends the CLI's input, waits for it to exit and removes the session's containers and temp home. Then the [`RunResult`](./run-result) is in `live.result`. Without `output`, its `stdout` holds every line the CLI wrote, events included.

- `output` is as for [`run()`](./run): the CLI's stdout and stderr go straight to `stdout.txt` and `stderr.txt`, the proxy's output to `proxy.log`, and the transcripts to `transcripts/`. Events are read by following `stdout.txt`. `live.result` then holds only `exit_code` and `image`; read the files for the rest. A Docker error points to `stderr.txt`. Omit `output` to keep the output in `live.result` as before; the proxy log and transcripts are then deleted with the temp home.
- `timeout` covers the whole block, every turn, and the wait for the CLI to exit. When it runs out, the session tears down as a cancel does and raises [`botbox.Timeout`](./botbox#timeout), whose `result` is `live.result`.
- Cancelling the task, or an `asyncio.timeout` firing, mid-turn or between turns, kills the CLI and tears the session down, even through a second cancel. So does an exception out of the block. `live.result` still holds the output captured so far (without `output`), with `exit_code` -1.
- A Docker client that dies while the daemon is up, or a container that never started, raises `DockerException` when the block ends, as `run()` does.
- Raises `TypeError` for an agent with no session mode; `CodexAgent` raises `NotImplementedError`. Both before anything is built.

```python
async with Botbox(ClaudeAgent()).session() as live:
    async for event in live.stream("Fix the failing test."):
        print(event["type"])
    events = await live.message("Now run the whole suite.")
print(live.result.exit_code)
```

## `Session`

```python
async for event in live.stream(text: str): ...
await live.message(text: str) -> list[dict[str, Any]]
live.result -> RunResult | None
```

`live.stream(text)` sends `text` and yields each event as the CLI prints it, one per JSON line on its stdout. It ends after the event that ends the agent's turn. Lines that aren't JSON objects are skipped, and stay in the result's `stdout` or in `stdout.txt`. If the CLI exits mid-turn, the stream ends with what arrived; with `output`, lines not yet read when it exits are only in `stdout.txt`. Leave the loop early and the rest of that turn is read and dropped before the next message is sent. `await live.message(text)` collects a whole turn into a list. Run one turn at a time. A turn has no timeout of its own. Wrap one in `asyncio.timeout` to bound it, which ends the session.

Events come from inside the box, and any process there can forge one. See [Forged session events](../threat-model#forged-session-events).
