# `session()`

```python
async with box.session(
    *,
    mounts: Sequence[tuple[str | Path, str | Path, Literal["ro", "rw"]]] = (),
    workdir: str | Path | None = None,
) as live: ...
```

Starts the agent's CLI in its session mode and holds it open, yielding a [`Session`](#session). `mounts` and `workdir` are as for [`run()`](./run), and so are the lockdown, labels and temp home. Background processes the agent starts live until the session ends. Leaving the block ends the CLI's input, waits for it to exit and removes the session's containers and temp home. Then the [`RunResult`](./run-result) is in `live.result`. Its `stdout` holds only the lines the CLI wrote that aren't events, such as stray output and errors, and only the last 1 MiB of them. Events come from `stream()` and `message()`.

- Cancelling the task, or an `asyncio.timeout` firing, mid-turn or between turns, kills the CLI and tears the session down, even through a second cancel. So does an exception out of the block. `live.result` still holds the output, transcripts and proxy log captured so far, with `exit_code` -1; if reading them fails, a warning, and the original error propagates.
- A line on the CLI's stdout longer than 1 GiB kills the CLI and raises `botbox.OutputLimitExceeded` from the read that hit it, then again from every later read and from leaving the block. The teardown is as for an exception out of the block.
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

`live.stream(text)` sends `text` and yields each event as the CLI prints it, one per JSON line on its stdout. It ends after the event that ends the agent's turn. Lines that aren't JSON objects are skipped, and kept for the result's `stdout`. If the CLI exits mid-turn, the stream ends with what arrived. Leave the loop early and the rest of that turn is read and dropped before the next message is sent. `await live.message(text)` collects a whole turn into a list, so it holds every event of the turn; `stream()` holds only the line it is reading. A session drops each line once it is read, and stops reading the CLI while 1 MiB of its output waits unread, so leaving a turn early doesn't pile output up. Run one turn at a time. There is no timeout; wrap a turn in `asyncio.timeout` to bound it, which ends the session.

Events come from inside the box, and any process there can forge one. See [Forged session events](../threat-model#forged-session-events).
