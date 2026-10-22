# Reference

The Python API, all asyncio: `Botbox`, `build()`, `run()`, `RunResult`, `session()` and `Session`. The agent classes are on the [harness pages](../harnesses/).

## `Botbox`

```python
Botbox(agent: Agent, *, dockerfile: str | Path | None = None, allow: Sequence[str] = ())
```

| Argument     | What it is                                                     |
| ------------ | -------------------------------------------------------------- |
| `agent`      | Which harness. See [Harnesses](../harnesses/).                 |
| `dockerfile` | Your layer on top of the agent's image. Build context is the Dockerfile's directory. Must end as `USER user` and leave the agent's home where it is. |
| `allow`      | Hostnames the proxy admits, in addition to the agent's own.    |

`Botbox` is an async context manager. Inside `async with Botbox(...) as box:`, SIGTERM cancels the task that entered the block, so a run or session in progress tears down, then the block raises `SystemExit(143)`. Any other cancel propagates as usual. A SIGTERM handler you set yourself is left alone, and off the main thread nothing changes. `build()`, `run()` and `session()` work without the block too.

Don't fork while a run is in progress. A forked child inherits the run's pipes and the event loop's state. Start a process pool before any run, or use the `spawn` or `forkserver` start method.

A sync caller wraps each call in `asyncio.run(...)`.

## `build()`

```python
await box.build() -> str
```

Builds the agent's image, then your `dockerfile` on top, and returns the tag. `run()` and `session()` call this every time; Docker's layer cache keeps an unchanged build fast.

Concurrent builds of one tag, from any process, take turns without blocking the event loop. Cancelling the task, or an `asyncio.timeout` firing, stops the build in progress. A failed build raises `botbox.DockerException` with the build's error in `stderr`.

```python
tag = await Botbox(ClaudeAgent(), dockerfile="./Dockerfile").build()
```

## `run()`

```python
await box.run(
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

Returns a [`RunResult`](#runresult). A non-zero exit is a normal `RunResult`.

- Cancelling the task, or an `asyncio.timeout` firing, removes the run's containers and temp home, then the cancel propagates. A second cancel doesn't cut the teardown short. No `RunResult` comes back.
- The run waits for the agent's container to stop, reads its exit code, then removes it. Both containers carry the label `botbox.run=<token>`. The temp home is `<token>/` in `botbox-<uid>/` under the system temp directory. A process killed outright (SIGKILL) leaves them behind, for [`reap()`](#reap) to remove. Each run calls it first.
- A Docker failure during setup raises `botbox.DockerException`, with the command in `docker_command`, its `return_code` and its `stderr` as text. So does a Docker client that dies or is killed while the daemon is still up, and a container that never started: an image the daemon can't find raises with `return_code` 125. If the daemon goes away mid-run, `exit_code` is -1.
- A teardown step that fails after the command ran is a `RuntimeWarning`, and the result still comes back. So is a container removal the daemon hasn't finished within 30 seconds, and a proxy log that can't be copied, which leaves `proxy` empty.

```python
async with asyncio.timeout(600):
    result = await Botbox(ClaudeAgent()).run("claude -p 'fix the failing test'")
```

## `RunResult`

Nothing parsed. The transcript and proxy log stay on disk, in a temp directory the result owns.

| Field       | What it is                                                           |
| ----------- | -------------------------------------------------------------------- |
| `stdout`    | The command's standard output.                                       |
| `stderr`    | The command's standard error.                                        |
| `exit_code` | The command's exit code.                                             |
| `image`     | `str`: the tag that ran: your layer's when `dockerfile` is given, else the agent's. |
| `files`     | `Path`: the result's temp directory.                                 |
| `transcript`| `Path`: `files / "transcript"`. The transcript files, at their paths relative to the agent's home. |
| `proxy`     | `Path`: `files / "proxy.log"`. Every connection, admitted or refused. |

```python
result.save(dest)   # copy `files` to `dest`, which must not exist yet; returns the path
result.cleanup()    # delete `files` now
with result: ...    # delete `files` when the block ends
```

`files` is deleted when the result is garbage collected, as `tempfile.TemporaryDirectory` does. A path into it is only good while you hold the result. To keep the files, `save()` them. A process killed outright leaves the directory, `botbox-result-*` in the system temp directory.

The container is removed once its exit code is read; what it wrote outside the mounts and the agent's home goes with it. If the Docker daemon goes away mid-run, `run()` returns what arrived, with `exit_code` -1.

## `session()`

```python
async with box.session(
    *,
    mounts: Sequence[tuple[str | Path, str | Path, Literal["ro", "rw"]]] = (),
    workdir: str | Path | None = None,
) as live: ...
```

Starts the agent's CLI in its session mode and holds it open, yielding a [`Session`](#session). `mounts` and `workdir` are as for [`run()`](#run), and so are the lockdown, labels and temp home. Background processes the agent starts live until the session ends. Leaving the block ends the CLI's input, waits for it to exit and removes the session's containers and temp home. Then the `RunResult` is in `live.result`; its `stdout` holds every line the CLI wrote, events included.

- Cancelling the task, or an `asyncio.timeout` firing, mid-turn or between turns, kills the CLI and tears the session down, even through a second cancel. So does an exception out of the block. `live.result` still holds the output, transcripts and proxy log captured so far, with `exit_code` -1; if capturing them fails, a warning, and the original error propagates.
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

`live.stream(text)` sends `text` and yields each event as the CLI prints it, one per JSON line on its stdout. It ends after the event that ends the agent's turn. Lines that aren't JSON objects are skipped, and stay in the result's `stdout`. If the CLI exits mid-turn, the stream ends with what arrived. Leave the loop early and the rest of that turn is read and dropped before the next message is sent. `await live.message(text)` collects a whole turn into a list. Run one turn at a time. There is no timeout; wrap a turn in `asyncio.timeout` to bound it, which ends the session.

Events come from inside the box, and any process there can forge one. See [Forged session events](../threat-model#forged-session-events).

## `reap()`

```python
await botbox.reap() -> list[str]
```

Removes what runs whose owner died left behind, and returns their tokens. A run's containers go, in any state, and so does its temp home, with the credentials staged in it. Every `run()` and `session()` calls it before it builds. Call it yourself to clean up without starting a run.

- A run counts as dead when its lock is free. The owner holds an exclusive `flock` on `botbox-<uid>/<token>.lock` for the run's whole life, and the kernel drops it however the owner dies. There are no pid or host checks, so an owner in another container or on another host never looks dead.
- It sweeps only the current user's runs, and only containers on the daemon `docker` reaches now. A dead run whose containers live on another daemon loses its temp home, and the containers stay.
- A run it can't clear is a `RuntimeWarning`, and the next sweep tries again.
- Runs that died before this release left their temp homes as `botbox-<token>-*` in the system temp directory. Those aren't swept.

See also: [Guides](../guide/), [How It Works](../explanation/).
