# Migrating a consumer to async botbox

How code that calls botbox moves from the sync `Botbox` to the async API. The plan is epic #79.

This was written before the spikes (#80, #81, #82) reported. Anything marked *provisional* may still change.

## Timeline and pinning

1. **Additive (0.0.x patches).** `AsyncBotbox` ships beside the sync `Botbox`: `build()` (#83), then `run()` (#84), then `session()` (#85). Nothing breaks.
2. **The switch (0.1.0, #86).** The sync API is removed. `AsyncBotbox` is renamed `Botbox`. python-on-whales is no longer a dependency.

What to do:

- Pin `botbox>=0.0.25,<0.1` now. The upper bound keeps the switch from landing on you unannounced.
- Move to `AsyncBotbox` during phase 1. Raise the floor to the first release that has every method you call.
- At 0.1.0, change `AsyncBotbox` to `Botbox` and move the pin to `>=0.1,<0.2`. Whether `AsyncBotbox` stays as an alias in 0.1 is *provisional*; assume it doesn't.
- If your own code imports `python_on_whales`, declare it as your own dependency. botbox stops pulling it in at 0.1.0.

## What stays the same

- Agents (`ClaudeAgent`, `CodexAgent`, `PiAgent`, subclasses of them) and their arguments.
- `Botbox` arguments: `dockerfile`, `allow`. `run()` and `session()` arguments: `mounts`, `workdir`.
- `RunResult` is still a frozen dataclass. `asdict(result)` works. Fixtures that build one by keyword or by position keep working.
- `exit_code == -1` (the daemon went away mid-run) is still a normal result, not an exception.

*Provisional:* what `RunResult.container` holds once agent containers run with `--rm` (the follow-up to #74). Don't build on removing that container yourself.

## build

```python
# before
tag = Botbox(agent, dockerfile=DOCKERFILE).build()

# after
tag = await AsyncBotbox(agent, dockerfile=DOCKERFILE).build()
```

Concurrent builds of one tag still take turns, across processes, without blocking the loop.

## run

```python
# before
with Botbox(agent, dockerfile=DOCKERFILE) as box:
    result = box.run(command, mounts=mounts, workdir="/target")

# after
async with AsyncBotbox(agent, dockerfile=DOCKERFILE) as box:
    result = await box.run(command, mounts=mounts, workdir="/target")
```

A function that returned a `RunResult` becomes `async def` and every caller up the stack awaits it. That spread is the real cost of the migration. Stop it at one entry point (see "Calling from sync code").

## session

```python
# before
with Botbox(agent) as box:
    with box.session(mounts=mounts, workdir="/solution") as live:
        events = live.message(text)
        result = live.close()

# after
async with AsyncBotbox(agent) as box:
    async with box.session(mounts=mounts, workdir="/solution") as live:
        events = await live.message(text)
    result = live.result
```

`await live.message(text)` still collects one turn and returns its events.

*Provisional:* how you get the session's `RunResult`. The sync `close()` returned it. The async shape (`live.result` after the block, or `await live.aclose()`) is settled in #85.

A session opened without `with` and closed in a `finally` (a session held open across a generator) becomes an `@asynccontextmanager`:

```python
@asynccontextmanager
async def open_session(config) -> AsyncIterator[Session]:
    async with AsyncBotbox(agent, dockerfile=DOCKERFILE) as box:
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

Breaking out of the `async for` early is *provisional*: whether the rest of the turn is drained or the session is torn down is settled in #85. Until then, consume the whole turn.

## Calling from sync code

Put `asyncio.run` at your entry point (the CLI command, the script's `main`) and nowhere else:

```python
def cli(...):
    asyncio.run(run_experiment(config))
```

- `asyncio.run` fails inside a running loop (Jupyter, an async framework). There, `await` directly.
- **Thread pools.** Each thread can `asyncio.run` its own loop. It works, but cancellation and timeouts stop at the thread boundary, which is what async is for. Replace the pool with a `TaskGroup`.
- **Process pools.** Each worker calls `asyncio.run(...)` around its own work. Nothing else changes. Use this when you want the work in another process for reasons beyond botbox.
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

*Provisional:* SIGTERM handling. The sync `with Botbox` turns SIGTERM into `SystemExit` so cleanup runs. The async plan is `loop.add_signal_handler`, mapping SIGTERM to cancellation. Owner SIGKILL ending the run depends on #80.

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

*Provisional:* `DockerException`. Today `botbox.DockerException` is python_on_whales' class, with its constructor `DockerException(command, return_code)`. After 0.1.0 it will be botbox's own. Catch `botbox.DockerException`, never `python_on_whales.exceptions.DockerException`. Tests that construct one with the python_on_whales signature will need a change.

## Testing

Integration tests that patch `python_on_whales.docker.*` to fake the daemon stop working at 0.1.0. botbox no longer calls those functions, so the patches miss and the tests try to reach a real daemon. Don't port them to patch aiodocker either. botbox's Docker boundary is internal, and the spikes may route builds and attaches through the `docker` CLI. Delete them.

Replace them with two layers:

- **Unit tests patch botbox at your own module.** `patch(..., autospec=True)` gives `AsyncMock` for async methods:

  ```python
  @pytest.fixture
  def botbox():
      with patch("my_pkg.runner.AsyncBotbox", autospec=True) as mock:
          mock.return_value.__aenter__.return_value = mock.return_value
          yield mock

  async def it_returns_the_run_result(botbox):
      assert await call() is botbox.return_value.run.return_value
  ```

- **Fakes** for orchestration tests: make the methods `async def`, `__aenter__`/`__aexit__` instead of `__enter__`/`__exit__`, and `stream()` an async generator. `RunResult` fixtures stay as they are.
- **e2e against real Docker** for the few behaviors that only exist there.

Async tests need a pytest plugin. Set `asyncio_mode = "auto"` with pytest-asyncio.

## botbox internals

Only names in `botbox.__all__` are public. `botbox.lockdown`, `botbox.collect`, `botbox.build_lock`, `botbox.Session.read_transcript` and the `botbox.Botbox` module path are internal. They are rewritten during the port, and no migration note covers them. If you import one, stop now, or open an issue for what you need.

A vendored copy of botbox's lockdown in your own code keeps working, since it carries its own python_on_whales calls. It won't get botbox's fixes.

## Checklist

- [ ] Pin `botbox>=0.0.25,<0.1`.
- [ ] Declare `python-on-whales` if you import it directly.
- [ ] Remove imports of botbox internals.
- [ ] Switch to `AsyncBotbox`; add `async`/`await` up to one `asyncio.run`.
- [ ] Move your own blocking work off the loop.
- [ ] Replace `turn_ended` side effects with `live.stream()`.
- [ ] Replace thread pools and sequential sample loops with a `TaskGroup`.
- [ ] Delete tests that patch python_on_whales; patch `AsyncBotbox` at your module.
- [ ] At 0.1.0: rename to `Botbox`, re-pin `<0.2`.
