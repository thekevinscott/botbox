# `run()`

```python
await box.run(
    command: str,
    *,
    mounts: Sequence[tuple[str | Path, str | Path, Literal["ro", "rw"]]] = (),
    workdir: str | Path | None = None,
    timeout: float | None = None,
) -> RunResult
```

| Argument  | What it is                                                              |
| --------- | ----------------------------------------------------------------------- |
| `command` | Shell command line, run as `sh -c`, passed through unchanged. |
| `mounts`  | Bind mounts: host path, container path, mode. A missing host path is created as a dir owned by you. |
| `workdir` | Where the command starts. Must be a mounted path or inside one; otherwise `run()` raises. Defaults to the agent's home. |
| `timeout` | Seconds the run may take once the image is built. Defaults to the box's [`timeout`](./botbox). |

Returns a [`RunResult`](./run-result). A non-zero exit is a normal `RunResult`.

- When `timeout` runs out, the run tears down as a cancel does and raises [`botbox.Timeout`](./botbox#timeout). Its `result` holds the output, transcript and proxy log so far, with `exit_code` -1.
- Cancelling the task, or an `asyncio.timeout` firing, removes the run's containers and temp home, then the cancel propagates. A second cancel doesn't cut the teardown short. No `RunResult` comes back.
- The run waits for the agent's container to stop, reads its exit code, then removes it. Both containers carry the label `botbox.run=<token>`. The temp home is `<token>/` in `botbox-<uid>/` under the system temp directory. A process killed outright (SIGKILL) leaves them behind, for [`reap()`](./reap) to remove. Each run calls it first.
- A Docker failure during setup raises `botbox.DockerException`, with the command in `docker_command`, its `return_code` and its `stderr` as text. So does a Docker client that dies or is killed while the daemon is still up, and a container that never started: an image the daemon can't find raises with `return_code` 125. If the daemon goes away mid-run, `exit_code` is -1.
- A teardown step that fails after the command ran is a `RuntimeWarning`, and the result still comes back. So is a container removal the daemon hasn't finished within 30 seconds, and a proxy log that can't be read, which leaves `proxy` empty.

```python
try:
    result = await Botbox(ClaudeAgent(), timeout=600).run("claude -p 'fix the failing test'")
except botbox.Timeout as timed_out:
    result = timed_out.result
```
