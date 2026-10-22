# Reference

The Python API: `Botbox`, `run()`, `RunResult`, `session()`, `Session`, `build()`, `AsyncBotbox` and `AsyncSession`. The agent classes are on the [harness pages](../harnesses/).

## `Botbox`

```python
Botbox(agent: Agent, *, dockerfile: str | Path | None = None, allow: Sequence[str] = ())
```

| Argument     | What it is                                                     |
| ------------ | -------------------------------------------------------------- |
| `agent`      | Which harness. See [Harnesses](../harnesses/).                 |
| `dockerfile` | Your layer on top of the agent's image. Build context is the Dockerfile's directory. Must end as `USER user` and leave the agent's home where it is. |
| `allow`      | Hostnames the proxy admits, in addition to the agent's own.    |

`Botbox` is a context manager. Inside `with Botbox(...) as box:`, SIGTERM unwinds a run or session in progress so it tears down. Agent containers remove themselves when they exit, so there is nothing left to remove on exit.

## `run()`

```python
box.run(
    command: str,
    *,
    mounts: Sequence[tuple[str | Path, str | Path, Literal["ro", "rw"]]] = (),
    workdir: str | Path | None = None,
) -> RunResult
```

| Argument  | What it is                                                              |
| --------- | ----------------------------------------------------------------------- |
| `command` | Shell command line, run as `sh -c`, passed through unchanged. |
| `mounts`  | Bind mounts: host path, container path, mode. Missing host paths raise. |
| `workdir` | Where the command starts. Must be a mounted path or inside one; otherwise `run()` raises. Defaults to the agent's home. |

Returns a [`RunResult`](#runresult). A non-zero exit is a normal `RunResult`. Raises only when setup fails or the run is interrupted. A Docker failure during setup raises `botbox.DockerException` (python-on-whales' own class, re-exported).

## `RunResult`

Nothing parsed.

| Field       | What it is                                                           |
| ----------- | -------------------------------------------------------------------- |
| `stdout`    | The command's standard output.                                       |
| `stderr`    | The command's standard error.                                        |
| `exit_code` | The command's exit code.                                             |
| `transcript`| `dict[str, str]`: path relative to the agent's home → file contents. |
| `proxy`     | `str`: the proxy log. Every connection, admitted or refused.         |
| `image`     | `str`: the tag that ran: your layer's when `dockerfile` is given, else the agent's. |

The container removes itself when it exits; what it wrote outside the mounts and the agent's home goes with it. If the Docker daemon dies mid-run, `run()` returns what arrived, with `exit_code` -1 and the Docker client's error at the end of `stderr`. If the daemon refuses the container, `exit_code` is the client's 125, 126 or 127 and `stderr` holds the daemon's error.

## `session()`

```python
box.session(
    *,
    mounts: Sequence[tuple[str | Path, str | Path, Literal["ro", "rw"]]] = (),
    workdir: str | Path | None = None,
) -> Session
```

Starts the agent's CLI in its session mode and holds it open. `mounts` and `workdir` are as for [`run()`](#run). Background processes the agent starts live until the session closes. Raises `TypeError` for an agent with no session mode; `CodexAgent` raises `NotImplementedError`. The container removes itself when the CLI exits.

## `Session`

| Member              | What it is                                                                 |
| ------------------- | -------------------------------------------------------------------------- |
| `message(text)`     | Sends `text`, blocks until the turn ends, and returns the turn's events: `list[dict]`, one per JSON line on the CLI's stdout. Lines that aren't JSON objects are skipped. If the CLI exits mid-turn, returns what arrived. |
| `close()`           | Ends the CLI's input, waits for it to exit, and returns a [`RunResult`](#runresult). Safe to call twice. |
| `result`            | The `RunResult` once closed, else `None`.                                  |

`Session` is a context manager; leaving the block calls `close()`. The `RunResult`'s `stdout` holds every line the CLI wrote, events included. There is no timeout: a turn that never ends blocks `message()`.

## `build()`

```python
box.build() -> str
```

Builds the agent's image, then your `dockerfile` on top, and returns the tag. `run()` calls this every time.

Concurrent builds of one tag, from any process, take turns. Safe to call from parallel runs.

## `AsyncBotbox`

```python
AsyncBotbox(agent: Agent, *, dockerfile: str | Path | None = None, allow: Sequence[str] = ())
await box.build() -> str
await box.run(command: str, *, mounts: Sequence[Mount] = (), workdir: str | Path | None = None) -> RunResult
async with box.session(*, mounts: Sequence[Mount] = (), workdir: str | Path | None = None) as live: ...
```

`Botbox` for asyncio, with the same arguments. It has `build()`, `run()` and `session()`.

`AsyncBotbox` is an async context manager. Inside `async with AsyncBotbox(...) as box:`, SIGTERM cancels the task that entered the block, so a run or session in progress tears down, then the block raises `SystemExit(143)`. Any other cancel propagates as usual. A SIGTERM handler you set yourself is left alone, and off the main thread nothing changes. `run()` and `session()` work without the block too.

`await box.build()` builds the same images as `build()` and returns the same tag. Concurrent builds of one tag take turns with each other and with sync `build()`s, from any process, without blocking the event loop. Cancelling the task, or an `asyncio.timeout` firing, stops the build in progress. A failed build raises `DockerException` with the build's error in `stderr`.

```python
tag = await AsyncBotbox(ClaudeAgent(), dockerfile="./Dockerfile").build()
```

`await box.run(command)` is [`run()`](#run) for asyncio: the same lockdown, home, mounts and `RunResult`. Where it differs:

- Cancelling the task, or an `asyncio.timeout` firing, removes the run's containers and temp home, then the cancel propagates. A second cancel doesn't cut the teardown short. No `RunResult` comes back.
- The containers don't remove themselves. The run waits for the agent's container to stop, reads its exit code, then removes it. Both containers carry the label `botbox.run=<token>`, and the temp home is named `botbox-<token>-*`. A process killed outright (SIGKILL) leaves them stopped, for a sweep to remove.
- If the Docker client dies or is killed while the daemon is still up, `run()` raises `DockerException` instead of returning. So does a container that never started: an image the daemon can't find raises `DockerException` with `return_code` 125, where `Botbox.run()` returns a `RunResult` with `exit_code` 125. If the daemon goes away mid-run, `exit_code` is -1, as for `run()`.
- A teardown step that fails after the command ran is a `RuntimeWarning`, and the result still comes back. So is a container removal the daemon hasn't finished within 30 seconds, and a proxy log that can't be read, which leaves `proxy` empty.
- Don't fork while a run is in progress. A forked child inherits the run's pipes and the event loop's state. Start a process pool before any run, or use the `spawn` or `forkserver` start method.

```python
async with asyncio.timeout(600):
    result = await AsyncBotbox(ClaudeAgent()).run("claude -p 'fix the failing test'")
```

`async with box.session() as live` is [`session()`](#session) for asyncio. It yields an [`AsyncSession`](#asyncsession). The lockdown, labels, temp home and teardown are the same as for `run()`. Leaving the block ends the CLI's input, waits for it to exit and removes the session's containers and temp home. Then the `RunResult` is in `live.result`. Where it differs from `Botbox.session()`:

- Cancelling the task, or an `asyncio.timeout` firing, mid-turn or between turns, kills the CLI and tears the session down, even through a second cancel. So does an exception out of the block. `live.result` stays `None`.
- There is no `close()`. The block's end is the close.
- A Docker client that dies while the daemon is up, or a container that never started, raises `DockerException` when the block ends. `run()` raises in the same cases.
- `session()` raises `TypeError` for an agent with no session mode, and `CodexAgent` raises `NotImplementedError`, both before anything is built.

```python
async with AsyncBotbox(ClaudeAgent()).session() as live:
    async for event in live.stream("Fix the failing test."):
        print(event["type"])
    events = await live.message("Now run the whole suite.")
print(live.result.exit_code)
```

## `AsyncSession`

```python
async for event in live.stream(text: str): ...
await live.message(text: str) -> list[dict[str, Any]]
live.result -> RunResult | None
```

`live.stream(text)` sends `text` and yields each event as the CLI prints it. It ends after the event that ends the agent's turn. Lines that aren't JSON objects are skipped, and stay in the result's `stdout`. If the CLI exits mid-turn, the stream ends with what arrived. Leave the loop early and the rest of that turn is read and dropped before the next message is sent. `await live.message(text)` collects a whole turn into a list. Run one turn at a time. There is no timeout; wrap a turn in `asyncio.timeout` to bound it, which ends the session.

See also: [Guides](../guide/), [How It Works](../explanation/).
