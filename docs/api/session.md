# `session()`

```python
async with box.session(
    *,
    output: str | Path,
    mounts: Sequence[tuple[str | Path, str | Path, Literal["ro", "rw"]]] = (),
    workdir: str | Path | None = None,
    timeout: float | None = None,
) as live: ...
```

Starts the agent's CLI in its session mode and holds it open, yielding a [`Session`](#session). `mounts`, `workdir` and `timeout` are as for [`run()`](./run), and so are the lockdown, labels and temp home. Background processes the agent starts live until the session ends. Leaving the block ends the CLI's input, waits for it to exit and removes the session's containers and temp home. Then the [`RunResult`](./run-result) is in `live.result`, and `stdout.txt` holds every line the CLI wrote, events included.

- `output` is required, and as for [`run()`](./run): the CLI's stdout and stderr go straight to `stdout.txt` and `stderr.txt`, the proxy's output to `proxy.log`, and the transcripts to `transcripts/`. Events are read by following `stdout.txt`. Read the files for what the session left. A Docker error points to `stderr.txt`.
- `timeout` covers the whole block, every turn, and the wait for the CLI to exit. When it runs out, the session tears down as a cancel does and raises [`botbox.Timeout`](./botbox#timeout), whose `result` is `live.result`.
- Cancelling the task, or an `asyncio.timeout` firing, mid-turn or between turns, kills the CLI and tears the session down, even through a second cancel. So does an exception out of the block. `live.result` has `exit_code` -1, and what was written so far stays in `output`.
- A Docker client that dies while the daemon is up, or a container that never started, raises `DockerException` when the block ends, as `run()` does.
- Raises `TypeError` for an agent with no session mode; `CodexAgent` raises `NotImplementedError`. Both before anything is built.

```python
async with Botbox(ClaudeAgent()).session(output="runs/fix") as live:
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

`live.stream(text)` sends `text` and yields each event as the CLI prints it, one per JSON line on its stdout. It ends after the event that ends the agent's turn. Lines that aren't JSON objects are skipped, and stay in `stdout.txt`. If the CLI exits mid-turn, the stream ends with what arrived; lines not yet read when it exits are only in `stdout.txt`. Leave the loop early and the rest of that turn is read and dropped before the next message is sent. `await live.message(text)` collects a whole turn into a list. Run one turn at a time. A turn has no timeout of its own. Wrap one in `asyncio.timeout` to bound it, which ends the session.

Events come from inside the box, and any process there can forge one. See [Forged session events](../threat-model#forged-session-events).
