# `run()`

```python
await box.run(
    command: str,
    *,
    output: str | Path | None = None,
    mounts: Sequence[tuple[str | Path, str | Path, Literal["ro", "rw"]]] = (),
    workdir: str | Path | None = None,
    timeout: float | None = None,
    keep: str | None = None,
) -> RunResult
```

| Argument  | What it is                                                              |
| --------- | ----------------------------------------------------------------------- |
| `command` | Shell command line, run as `sh -c`, passed through unchanged. |
| `output` | Optional host directory for `stdout.txt`, `stderr.txt`, `proxy.log` and `transcripts/`. Created with missing parents; relative paths resolve from the working directory. A path containing `:` raises `ValueError` before anything is touched. |
| `mounts`  | Bind mounts: host path, container path, mode. A missing host path is created as a dir owned by you. |
| `workdir` | Where the command starts. Must be a mounted path or inside one; otherwise `run()` raises. Defaults to the agent's home. |
| `timeout` | Seconds the run may take once the image is built. Defaults to the box's [`timeout`](./botbox). |
| `keep` | Name for the agent container to retain after exit, cancellation or timeout. The proxy and temp directory are still removed. |

Returns a [`RunResult`](./run-result). A non-zero exit is a normal `RunResult`.

To continue on a kept container's filesystem, call `await box.restart(name, command, output=..., mounts=..., workdir=..., timeout=...)`. Restart commits the stopped container to an image, removes it and its old socket volume, then creates a new container under the same name with a fresh proxy and lockdown. The new container is kept. An existing name passed to `keep` raises during setup. The kept container's socket volume remains until restart or manual cleanup; remove the container before removing the volume.

The agent's staged home is included in the restart image. For agents with a `credential_source`, its staged credential is a placeholder. For agents whose credential is copied into the home, the image contains the real credential. Store and remove these images accordingly. Docker logging is disabled for agent containers, so `docker logs` on a kept container is empty; pass `output` to retain stdout and stderr.

With `output`, botbox copies stdout, stderr and the proxy's log there chunk by chunk as they
arrive (see [Output](../explanation/#output)). `output/transcripts/` is bind-mounted over the
agent's sessions directory, such as `~/.claude/projects`, so the CLI writes its transcripts
there directly.
botbox stages credentials outside the sessions directory, so nothing botbox writes to
`output` contains them. The agent can still print them into a stream or a transcript.
Everything in `output` is agent-written and untrusted, symlinks included: don't follow links
out of it. Read the files yourself when needed:

```python
from pathlib import Path

output = Path("runs/check")
result = await box.run("echo hello", output=output)
print((output / "stdout.txt").read_text())
```

`stdout.txt`, `stderr.txt` and `proxy.log` are created or truncated immediately after the
output directory is created or reused, before setup starts; other files in the directory,
`transcripts/` included, are preserved. Sessions already in `transcripts/` are visible to the
agent. To continue one, pass `resume=True` for the latest session or its ID for a specific one,
and use the same `workdir` on both runs:

```python
agent = ClaudeAgent()
box = Botbox(agent)
await box.run(agent.command("Remember this"), output="runs/first", workdir=agent.home)
await box.run(agent.command("Recall it", resume=True), output="runs/first", workdir=agent.home)
```

To continue from another run's sessions, copy its `transcripts/` into the new `output` first:

```python
import shutil

shutil.copytree("runs/first/transcripts", "runs/second/transcripts")
result = await box.run(agent.command("Recall it", resume=True), output="runs/second", workdir=agent.home)
```

Use a separate directory for each concurrent run. The
files remain after success, failure, timeout or cancellation. If build or credential
staging fails, all three are empty. `proxy.log` holds everything the proxy container printed,
its startup output included; if the proxy won't start, the error also carries the last 64 KiB
of it. An agent Docker failure puts the last 64 KiB of the agent's stderr in
`DockerException.stderr`; build and proxy setup failures carry their own diagnostics.

The streams and the proxy log are written first to the run's temp directory, under `TMPDIR`,
and copied to `output` as they arrive. A write to `output` that fails, a full disk say, is a
`RuntimeWarning`; that file stops there and the run carries on. A failure in the temp directory
raises. Omit `output` and the streams, transcripts and proxy log are deleted after the run.

- When `timeout` runs out, the run tears down as a cancel does and raises [`botbox.Timeout`](./botbox#timeout). Its `result` has `exit_code` -1; what the run left so far is in `output`.
- Cancelling the task, or an `asyncio.timeout` firing, removes the run's containers and temp directory, then the cancel propagates. With `keep`, the agent container and its socket volume remain. A second cancel doesn't cut the teardown short. No `RunResult` comes back.
- The run waits for the agent's container to stop, reads its exit code, then removes it. Both containers, and the `botbox-run-<token>` volume holding the proxy's socket, carry the label `botbox.run=<token>`. The temp directory is a `botbox-<token>-*` directory from Python's `tempfile`, under the system temp directory. A process killed outright (SIGKILL) leaves them behind; remove the containers and the volume by label.
- A Docker failure during setup raises `botbox.DockerException`, with the command in `docker_command`, its `return_code` and its `stderr` as text. So does a Docker client that dies or is killed, a container that never started (an image the daemon can't find raises with `return_code` 125), and a daemon that goes away mid-run.
- A teardown step that fails after the command ran is a `RuntimeWarning`, and the result still comes back. So is a container removal the daemon hasn't finished within 30 seconds.

```python
box = Botbox(ClaudeAgent(), timeout=600)
try:
    result = await box.run("claude -p 'fix the failing test'", output="runs/fix")
except botbox.Timeout as timed_out:
    result = timed_out.result
```
