# Reading the result

Pass `run()` an `output` directory. The command's stdout and stderr, the proxy log and the agent's transcripts are written there while it runs, and stay after it ends. Use a separate directory for each run: reusing one truncates `stdout.txt`, `stderr.txt` and `proxy.log`.

The streams and the proxy log are copies. botbox writes them first to the run's temp directory, under `TMPDIR`, and reads errors and session events from there. If a write to `output` fails, botbox warns and stops writing that file, and the run goes on. Keep `TMPDIR` on disk, not a tmpfs: a chatty agent fills memory otherwise.

```text
runs/first/
  stdout.txt
  stderr.txt
  proxy.log
  transcripts/
```

A whole run, start to finish. It needs a Claude Code login on the host, though the command never calls the model:

```python
import asyncio
from pathlib import Path

from botbox import Botbox, ClaudeAgent


async def main() -> None:
    output = Path("runs/hello")
    async with Botbox(ClaudeAgent()) as box:
        result = await box.run("echo hello; echo oops >&2; exit 3", output=output)
    print(result.exit_code)                      # 3
    print((output / "stdout.txt").read_text())   # hello
    print((output / "stderr.txt").read_text())   # oops


asyncio.run(main())
```

How the two copies are written: [Output](../explanation/#output).

`run()` returns a `RunResult`, which holds only the `exit_code`. Read everything else from the files.

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

Omit `output` and `run()` keeps none of the streams, transcripts or proxy log. They are still written to the temp directory while the run lasts. Only the `exit_code` comes back. Files the command wrote to your mounts stay.

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

Next: the [`RunResult` page](../api/run-result), or [how a run works](../explanation/#a-run).
