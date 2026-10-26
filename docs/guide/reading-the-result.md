# Reading the result

Pass `run()` an `output` directory. The command's stdout and stderr, the proxy log and the agent's transcripts are written there while it runs, and stay after it ends. Use a separate directory for each run: reusing one truncates `stdout.txt`, `stderr.txt` and `proxy.log`.

```text
runs/first/
  stdout.txt
  stderr.txt
  proxy.log
  transcripts/
```

`run()` returns a `RunResult`. Nothing is parsed. With `output`, its `stdout`, `stderr`, `transcript` and `proxy` are empty; read the files instead.

## Check the exit code

A non-zero exit is a normal `RunResult`, not an exception. API errors inside the container show up in `exit_code` and `stderr.txt`.

```python
from pathlib import Path

output = Path("runs/first")
result = await box.run(agent.command("Fix the failing test."), output=output)
if result.exit_code != 0:
    print((output / "stderr.txt").read_text())
```

## Read the transcript

The agent writes its transcripts straight into `output/transcripts/`. The agent wrote that folder, so skip symlinks: one can point at any host file you can read.

```python
for path in sorted((output / "transcripts").rglob("*.jsonl")):
    if not path.is_symlink():
        print(path, path.stat().st_size)
```

## Read the proxy log

`proxy.log` holds every connection, admitted or refused.

```python
print((output / "proxy.log").read_text())
```

## Without `output`

Omit `output` and the streams, transcripts and proxy log come back on the result instead: `stdout` and `stderr` as text, `transcript` as a `dict[str, str]` of path relative to the agent's home → file contents, and `proxy` as text.

## Keep what the run wrote

The container is removed once its exit code is read, along with anything written outside the mounts and the agent's home. To keep a file, have the command write it to a mount.

```python
await box.run(
    agent.command("Write a report to /out"),
    output="runs/report",
    mounts=[(out, "/out", "rw")],
    workdir="/out",
)
```

Next: the [`RunResult` page](../api/run-result) for every field, or [how a run works](../explanation/#a-run).
