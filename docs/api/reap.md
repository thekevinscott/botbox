# `reap()`

```python
await botbox.reap() -> list[str]
```

Removes what runs whose owner died left behind, and returns their tokens. A run's containers go, in any state, and so does its temp home, with the credentials staged in it. Every [`run()`](./run) and [`session()`](./session) calls it before it builds. Call it yourself to clean up without starting a run.

- A run counts as dead when its lock is free. The owner holds an exclusive `flock` on `botbox-<uid>/<token>.lock` for the run's whole life, and the kernel drops it however the owner dies. There are no pid or host checks, so an owner in another container or on another host never looks dead.
- It sweeps only the current user's runs, and only containers on the daemon `docker` reaches now. A dead run whose containers live on another daemon loses its temp home, and the containers stay.
- A run it can't clear is a `RuntimeWarning`, and the next sweep tries again.
- Runs that died before this release left their temp homes as `botbox-<token>-*` in the system temp directory. Those aren't swept.
