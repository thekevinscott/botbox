# Reading the result

`run()` returns a `RunResult` containing only `exit_code`. Pass a separate `output` folder for each run or session. Output is written there while the agent runs and remains after teardown, including cancellation and timeout.

```python
from pathlib import Path

output = Path("runs/first")
result = await box.run(agent.command("Fix the failing test."), output=output)
if result.exit_code != 0:
    print((output / "stderr.txt").read_text(errors="replace"))
print((output / "stdout.txt").read_text(errors="replace"))
```

A non-zero exit is a normal result. When a timeout raises `botbox.Timeout`, its `result.exit_code` is -1 and the files remain available.

## Read the transcript

`output/transcripts/` contains the files the agent writes into its sessions directory. Their names and format belong to the agent. botbox does not read or parse them. Treat them as agent-controlled files, including any links the agent creates.

## Read the proxy log

`output/proxy.log` records connections admitted or refused by the proxy.

```python
print((output / "proxy.log").read_text(errors="replace"))
```

## Keep other files

Use [read-write mounts](./mounting-directories) for other files the agent should leave behind. Unrelated files in the output folder belong to the caller and remain in place. Reusing a folder truncates `stdout.txt`, `stderr.txt`, and `proxy.log`; existing transcript files remain until the agent changes them.

See the [`RunResult` page](../api/run-result) and [how a run works](../explanation/#a-run).
