# `Botbox`

The Python API is all asyncio. The agent classes are on the [harness pages](../harnesses/).

```python
Botbox(
    agent: Agent,
    *,
    dockerfile: str | Path | None = None,
    allow: Sequence[str] = (),
    memory: str | None = "64g",
    pids: int | None = 32768,
)
```

| Argument     | What it is                                                     |
| ------------ | -------------------------------------------------------------- |
| `agent`      | Which harness. See [Harnesses](../harnesses/).                 |
| `dockerfile` | Your layer on top of the agent's image. Build context is the Dockerfile's directory. Must end as `USER user` and leave the agent's home where it is. |
| `allow`      | Hostnames the proxy admits, in addition to the agent's own.    |
| `memory`     | Memory cap on the agent's container, in `docker run --memory` form (`"4g"`, `"512m"`). Default `"64g"`. `None` for no cap. |
| `pids`       | Cap on processes and threads in the agent's container (`docker run --pids-limit`). Default `32768`. `None` for no cap. |

`memory` and `pids` apply to the agent's container in both [`run()`](./run) and [`session()`](./session). They keep a runaway agent from taking down the host. The defaults are deliberately high so no real workload trips them: lower them to what your agent needs. Builds and test suites inside the box can need several GiB. An agent killed for going over `memory` shows up as `exit_code` 137, along with a `RuntimeWarning` naming the container.

`Botbox` is an async context manager. Inside `async with Botbox(...) as box:`, SIGTERM cancels the task that entered the block, so a run or session in progress tears down, then the block raises `SystemExit(143)`. Any other cancel propagates as usual. A SIGTERM handler you set yourself is left alone, and off the main thread nothing changes. [`build()`](./build), [`run()`](./run) and [`session()`](./session) work without the block too.

Don't fork while a run is in progress. A forked child inherits the run's pipes and the event loop's state. Start a process pool before any run, or use the `spawn` or `forkserver` start method.

A sync caller wraps each call in `asyncio.run(...)`.
