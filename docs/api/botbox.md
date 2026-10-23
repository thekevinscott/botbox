# `Botbox`

The Python API is all asyncio. The agent classes are on the [harness pages](../harnesses/).

```python
Botbox(
    agent: Agent,
    *,
    dockerfile: str | Path | None = None,
    allow: Sequence[str] = (),
    stdout_limit: int = 100 * 2**30,
    stderr_limit: int = 100 * 2**30,
)
```

| Argument     | What it is                                                     |
| ------------ | -------------------------------------------------------------- |
| `agent`      | Which harness. See [Harnesses](../harnesses/).                 |
| `dockerfile` | Your layer on top of the agent's image. Build context is the Dockerfile's directory. Must end as `USER user` and leave the agent's home where it is. |
| `allow`      | Hostnames the proxy admits, in addition to the agent's own.    |
| `stdout_limit` | Most bytes of the command's stdout that `run()` holds in memory and returns. Default 100 GiB. |
| `stderr_limit` | The same for stderr. Default 100 GiB. |

`Botbox` is an async context manager. Inside `async with Botbox(...) as box:`, SIGTERM cancels the task that entered the block, so a run or session in progress tears down, then the block raises `SystemExit(143)`. Any other cancel propagates as usual. A SIGTERM handler you set yourself is left alone, and off the main thread nothing changes. [`build()`](./build), [`run()`](./run) and [`session()`](./session) work without the block too.

Don't fork while a run is in progress. A forked child inherits the run's pipes and the event loop's state. Start a process pool before any run, or use the `spawn` or `forkserver` start method.

A sync caller wraps each call in `asyncio.run(...)`.

## Output caps

botbox holds a run's output in memory until the command exits, so an agent that prints without end can exhaust the host. `stdout_limit` and `stderr_limit` bound that. Past a cap, only the last that many bytes are kept and the result's `truncated` is `True`. The run carries on and returns normally. A character split at the cut reads as `\ufffd`. A cap of 0 keeps nothing. A negative cap raises `ValueError`.

The 100 GiB defaults only exist so there is a ceiling. They are high on purpose, so no ordinary run is cut. Lower them to what your runs need. The caps apply to [`run()`](./run) only; [`session()`](./session) doesn't use them.

The proxy log is capped too, at its last 1 MiB. That cap is fixed.
