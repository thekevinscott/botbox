# `run()`

```python
await box.run(
    command: str,
    *,
    output: str | Path | None = None,
    mounts: Sequence[tuple[str | Path, str | Path, Literal["ro", "rw"]]] = (),
    workdir: str | Path | None = None,
    timeout: float | None = None,
) -> RunResult
```

| Argument  | What it is                                                              |
| --------- | ----------------------------------------------------------------------- |
| `command` | Shell command line, run as `sh -c`, passed through unchanged. |
| `output` | Optional host directory for `stdout.txt`, `stderr.txt`, `proxy.log` and `transcripts/`. Created with missing parents; relative paths resolve from the working directory. A path containing `:` raises `ValueError` before anything is touched. |
| `mounts`  | Bind mounts: host path, container path, mode. A missing host path is created as a dir owned by you. |
| `workdir` | Where the command starts. Must be a mounted path or inside one; otherwise `run()` raises. Defaults to the agent's home. |
| `timeout` | Seconds the run may take once the image is built. Defaults to the box's [`timeout`](./botbox). |

Returns a [`RunResult`](./run-result). A non-zero exit is a normal `RunResult`.

With `output`, stdout, stderr and the proxy's log go directly to files without being
captured in Python. `output/transcripts/` is bind-mounted over the agent's sessions
directory, such as `~/.claude/projects`, so the CLI writes its transcripts there directly.
botbox stages credentials outside the sessions directory, so nothing botbox writes to
`output` contains them. The agent can still print them into a stream or a transcript.
Everything in `output` is agent-written and untrusted, symlinks included: don't follow links
out of it. The `stdout`, `stderr` and `proxy` result fields are empty,
including in `Timeout.result`; the image field retains its usual behavior. Read the files
yourself when needed:

```python
from pathlib import Path

output = Path("runs/check")
result = await box.run("echo hello", output=output)
print((output / "stdout.txt").read_text())
```

`stdout.txt`, `stderr.txt` and `proxy.log` are created or truncated immediately after the
output directory is created or reused, before setup starts; other files in the directory,
`transcripts/` included, are preserved. Use a separate directory for each concurrent run. The
files remain after success, failure, timeout or cancellation. If build or credential
staging fails, all three are empty. `proxy.log` holds everything the proxy container printed,
its startup output included; if the proxy won't start, the error also carries the last 64 KiB
of it. Agent Docker failures put the absolute
`stderr.txt` path in `DockerException.stderr`; build and proxy setup failures still carry their own diagnostics.
Omit `output` to keep stdout, stderr and the proxy log in the result as before. Transcripts
are deleted with the temporary home.

- When `timeout` runs out, the run tears down as a cancel does and raises [`botbox.Timeout`](./botbox#timeout). Its `result` holds the output and proxy log so far, with `exit_code` -1. With `output`, its `stdout`, `stderr` and `proxy` are empty; read the files instead.
- Cancelling the task, or an `asyncio.timeout` firing, removes the run's containers and temp home, then the cancel propagates. A second cancel doesn't cut the teardown short. No `RunResult` comes back.
- The run waits for the agent's container to stop, reads its exit code, then removes it. Both containers carry the label `botbox.run=<token>`. The temp home is a `botbox-<token>-*` directory from Python's `tempfile`, under the system temp directory. A process killed outright (SIGKILL) leaves them behind; remove the containers by label.
- A Docker failure during setup raises `botbox.DockerException`, with the command in `docker_command`, its `return_code` and its `stderr` as text. So does a Docker client that dies or is killed while the daemon is still up, and a container that never started: an image the daemon can't find raises with `return_code` 125. If the daemon goes away mid-run, `exit_code` is -1.
- A teardown step that fails after the command ran is a `RuntimeWarning`, and the result still comes back. So is a container removal the daemon hasn't finished within 30 seconds, and, without `output`, a proxy log that can't be read, which leaves `proxy` empty.

```python
box = Botbox(ClaudeAgent(), timeout=600)
try:
    result = await box.run("claude -p 'fix the failing test'", output="runs/fix")
except botbox.Timeout as timed_out:
    result = timed_out.result
```
