# Migrating a consumer to async botbox

How code that calls botbox moves from the sync `Botbox` (0.0.x) to the async `Botbox` (0.1.0). The plan is epic #79.

## Timeline and pinning

- **Until 0.1.0:** 0.0.x patches, sync `Botbox` only. botbox is alpha, so these patches can still break things (#74, agent `--rm`). Read the migration fragments when you bump.
- **0.1.0 (#86):** `Botbox` is async. The sync API is gone. python-on-whales is no longer a dependency.

Nothing async was released before the switch. You migrate once, from sync 0.0.x straight to async 0.1.0. There is no release where both APIs exist.

What to do:

- Pin `botbox>=0.0.25,<0.1` now. The upper bound keeps the switch from landing on you unannounced. It does not hold off breaking patches before it.
- Migrate when you move to `>=0.1,<0.2`.
- If your own code imports `python_on_whales`, declare it as your own dependency. botbox stops pulling it in at 0.1.0.

## What stays the same

- Agents (`ClaudeAgent`, `CodexAgent`, `PiAgent`, subclasses of them) and their arguments.
- `Botbox` arguments: `dockerfile`, `allow`. `run()` and `session()` arguments: `mounts`, `workdir`.
- `RunResult` is still a frozen dataclass. `asdict(result)` works. Fixtures that build one by keyword or by position keep working.
- `exit_code == -1` (the daemon went away mid-run) is still a normal result, not an exception.

## build

```python
# 0.0.x
tag = Botbox(agent, dockerfile=DOCKERFILE).build()

# 0.1.0
tag = await Botbox(agent, dockerfile=DOCKERFILE).build()
```

Concurrent builds of one tag still take turns, across processes, without blocking the loop.

## run

```python
# 0.0.x
with Botbox(agent, dockerfile=DOCKERFILE) as box:
    result = box.run(command, mounts=mounts, workdir="/target")

# 0.1.0
async with Botbox(agent, dockerfile=DOCKERFILE) as box:
    result = await box.run(command, mounts=mounts, workdir="/target")
```

A function that returned a `RunResult` becomes `async def` and every caller up the stack awaits it. That spread is the real cost of the migration. Stop it at one entry point (see "Calling from sync code").

## session

```python
# 0.0.x
with Botbox(agent) as box:
    with box.session(mounts=mounts, workdir="/solution") as live:
        events = live.message(text)
        result = live.close()

# 0.1.0
async with Botbox(agent) as box:
    async with box.session(mounts=mounts, workdir="/solution") as live:
        events = await live.message(text)
    result = live.result
```

`await live.message(text)` still collects one turn and returns its events.

There is no `close()`. Leaving the block ends the session and sets `live.result`. If the block raises or is cancelled, `live.result` still holds what was captured, with `exit_code` -1.

A session opened without `with` and closed in a `finally` (a session held open across a generator) becomes an `@asynccontextmanager`:

```python
@asynccontextmanager
async def open_session(config) -> AsyncIterator[Session]:
    async with Botbox(agent, dockerfile=DOCKERFILE) as box:
        async with box.session(mounts=mounts, workdir="/solutions") as live:
            yield live
        save_result(live.result, config)
```

## Streaming

Sync sessions block until the turn ends. Code that wanted events as they arrived had to hook `Agent.turn_ended()` or set a callback on the agent. Drop that. Iterate instead:

```python
async with box.session() as live:
    async for event in live.stream(text):
        on_delta(event)
```

The iterator ends at the agent's turn end. `turn_ended()` goes back to being only the turn terminator. Don't use it for side effects.

Breaking out of the `async for` early keeps the session. The rest of that turn is read and dropped before the next message is sent.

## Calling from sync code

Put `asyncio.run` at your entry point (the CLI command, the script's `main`) and nowhere else:

```python
def cli(...):
    asyncio.run(run_experiment(config))
```

- `asyncio.run` fails inside a running loop (Jupyter, an async framework). There, `await` directly.
- **Thread pools.** Each thread can `asyncio.run` its own loop. It works, but cancellation and timeouts stop at the thread boundary, which is what async is for. Replace the pool with a `TaskGroup`.
- **Process pools.** Each worker calls `asyncio.run(...)` around its own work. Nothing else changes. Use this when you want the work in another process for reasons beyond botbox. Don't fork while a run is in progress: start the pool first, or use the `spawn` or `forkserver` start method.
- **Your own blocking calls** (a `subprocess.run` test suite, `shutil.copytree`, a sync HTTP client) now block every concurrent run. Wrap them in `asyncio.to_thread`, or use `asyncio.create_subprocess_exec`.
- Callbacks you pass in run on the loop. A slow `on_delta` stalls everything.

## Concurrency

Sequential loops over samples become a `TaskGroup`:

```python
async with asyncio.TaskGroup() as tg:
    tasks = [tg.create_task(evaluate(sample)) for sample in range(n)]
results = [t.result() for t in tasks]
```

If one task raises, the group cancels the rest, and their containers are torn down. If you want every outcome even when some fail, use `asyncio.gather(..., return_exceptions=True)` instead.

Bound the fan-out with an `asyncio.Semaphore`. The Docker daemon, its network pool and your API rate limits all cap how many runs make sense at once.

## Timeouts and cancellation

```python
async with asyncio.timeout(600):
    result = await box.run(command)
```

- Cancelling a run, or a timeout firing, tears down that run's containers and temp home. Then `CancelledError` (or `TimeoutError`) propagates.
- No `RunResult` comes back. Output and transcript from a cancelled run are lost. If you need partial output, don't cancel: let the run finish and bound it inside the agent.
- Teardown is shielded from a second cancel and takes a moment. Cancellation is not instant.
- Ctrl-C under `asyncio.run` cancels the main task, so it tears down like any cancel.
- Don't catch `CancelledError` without re-raising it.
- SIGTERM inside `async with Botbox(...)` cancels the task that entered the block, then raises `SystemExit(143)` once teardown is done. Outside the block, SIGTERM keeps Python's default and exits without teardown.

Owner SIGKILL ends the run within seconds and leaves its containers stopped, labelled `botbox.run=<token>`. botbox leaves them, and the temp home, for the caller.

## Errors

botbox raises plain exceptions. It does not raise `ExceptionGroup`s, even where it runs work concurrently inside.

Your own `TaskGroup` does wrap failures in an `ExceptionGroup`. That is standard asyncio. Catch with `except*`:

```python
try:
    async with asyncio.TaskGroup() as tg:
        ...
except* DockerException as group:
    ...
```

`botbox.DockerException` is botbox's own class: `DockerException(docker_command, return_code, stderr)`, with `stderr` as text. It is no longer python_on_whales' class, so `except python_on_whales.exceptions.DockerException` stops catching it. Catch `botbox.DockerException`. Tests that construct one with the python_on_whales signature need the new one.

## Testing

Integration tests that patch `python_on_whales.docker.*` to fake the daemon stop working at 0.1.0. botbox no longer calls those functions, so the patches miss and the tests try to reach a real daemon. Don't port them to patch botbox's Docker calls either; that boundary is internal. Delete them.

Replace them with two layers:

- **Unit tests patch botbox at your own module.** `patch(..., autospec=True)` gives `AsyncMock` for async methods:

  ```python
  @pytest.fixture
  def botbox():
      with patch("my_pkg.runner.Botbox", autospec=True) as mock:
          mock.return_value.__aenter__.return_value = mock.return_value
          yield mock

  async def it_returns_the_run_result(botbox):
      assert await call() is botbox.return_value.run.return_value
  ```

- **Fakes** for orchestration tests: make the methods `async def`, `__aenter__`/`__aexit__` instead of `__enter__`/`__exit__`, and `stream()` an async generator. `RunResult` fixtures stay as they are.
- **e2e against real Docker** for the few behaviors that only exist there.

Async tests need a pytest plugin. Set `asyncio_mode = "auto"` with pytest-asyncio.

## botbox internals

Only names in `botbox.__all__` are public. `botbox.lockdown`, `botbox.build_lock`, `botbox.read_transcript`, `botbox.docker` and the `botbox.Botbox` module path are internal. `botbox.collect` is gone, and `read_transcript` moved out of `botbox.Session`. No migration note covers them. If you import one, stop, or open an issue for what you need.

A vendored copy of botbox's lockdown in your own code keeps working, since it carries its own python_on_whales calls. It won't get botbox's fixes.

## Checklist

- [ ] Now: pin `botbox>=0.0.25,<0.1`, declare `python-on-whales` if you import it, and drop imports of botbox internals.
- [ ] At 0.1.0: re-pin `>=0.1,<0.2`; add `async`/`await` up to one `asyncio.run`.
- [ ] Move your own blocking work off the loop.
- [ ] Replace `turn_ended` side effects with `live.stream()`.
- [ ] Replace thread pools and sequential sample loops with a `TaskGroup`.
- [ ] Delete tests that patch python_on_whales; patch `Botbox` at your module.
