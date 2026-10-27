# `Botbox`

The Python API is all asyncio. The agent classes are on the [harness pages](../harnesses/).

```python
Botbox(
    agent: Agent,
    *,
    dockerfile: str | Path | None = None,
    allow: Sequence[str] = (),
    timeout: float | None = None,
    memory: str | None = None,
)
```

| Argument     | What it is                                                     |
| ------------ | -------------------------------------------------------------- |
| `agent`      | Which harness. See [Harnesses](../harnesses/).                 |
| `dockerfile` | Your layer on top of the agent's image. Build context is the Dockerfile's directory. Must end as `USER user` and leave the agent's home where it is. |
| `allow`      | Hostnames the proxy admits, in addition to the agent's own.    |
| `timeout`    | Seconds each [`run()`](./run) and [`session()`](./session) may take, counted once the image is built. `None` means no limit. A call's own `timeout` replaces it. |
| `memory`     | Agent container memory limit, such as `"16g"`. `None` leaves it uncapped. Swap is disabled when a limit is set. |

`Botbox` is an async context manager. Inside `async with Botbox(...) as box:`, SIGTERM cancels the task that entered the block, so a run or session in progress tears down, then the block raises `SystemExit(143)`. Any other cancel propagates as usual. A SIGTERM handler you set yourself is left alone, and off the main thread nothing changes. [`build()`](./build), [`run()`](./run) and [`session()`](./session) work without the block too.

Don't fork while a run is in progress. A forked child inherits the run's pipes and the event loop's state. Start a process pool before any run, or use the `spawn` or `forkserver` start method.

A sync caller wraps each call in `asyncio.run(...)`.

## `Timeout`

A run or session that runs out of time tears down as a cancel does, then raises `botbox.Timeout`. It is a `TimeoutError`, so `except TimeoutError` catches it. `result` holds a [`RunResult`](./run-result) with `exit_code` -1. `seconds` is the limit that ran out.
