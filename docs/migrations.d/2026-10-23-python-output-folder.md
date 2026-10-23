## Summary

`run()` and `session()` now write output live into a required caller-owned folder. Output stays available after cancellation, timeout or a killed owner. `RunResult` contains only `exit_code`; botbox no longer buffers output or reads transcripts into Python. Only a proxy startup failure reads the last 64 KiB of `proxy.log` for the error message.

## Required changes

Pass `output` by keyword, choosing a separate directory for each run or session:

```python
# Before
result = await box.run(command)
print(result.stdout)
async with box.session() as live:
    events = await live.message("hi")

# After
from pathlib import Path

output = Path("runs/first")
result = await box.run(command, output=output)
print((output / "stdout.txt").read_text(errors="replace"))
async with box.session(output="runs/second") as live:
    events = await live.message("hi")
```

Read stderr from `stderr.txt`, proxy logs from `proxy.log`, and agent files from `transcripts/`. Transcript paths are relative to the agent's sessions directory, not its home. Treat transcript files and links as agent-controlled.

Replace constructions of `RunResult(stdout, stderr, exit_code, transcript, proxy, image)` with `RunResult(exit_code)`. Remove reads of `stdout`, `stderr`, `transcript`, `proxy` and `image` from results, including `Timeout.result` and `Session.result`. For agent-client Docker errors, `DockerException.stderr` points to the stderr file instead of containing it.

Custom agents replace the `transcripts` glob with a `sessions_dir` path relative to the agent's home. Built-in paths are `.claude/projects`, `.codex/sessions` and `.pi/agent/sessions`.

## Deprecations removed

None. The removed result fields and transcript glob have no compatibility shim.

## Behavior changes without code changes

The output folder is created if missing. stdout, stderr and proxy.log are opened afresh for each invocation; transcript files and unrelated caller files remain. Credentials stay in the temporary home and are cleaned up as before. The output folder is never reaped.

Session event parsing uses `tail -n +1 -F`. Non-event lines remain on disk. When the CLI exits mid-turn, its last lines may not reach the event stream before it ends; they remain in stdout.txt. Unflushed output and power loss are outside the persistence guarantee.

## Verification

Run a command without calling a model:

```python
from pathlib import Path

output = Path("runs/check")
result = await box.run("echo hello; echo diagnostic >&2", output=output)
assert result.exit_code == 0
assert (output / "stdout.txt").read_text() == "hello\n"
assert (output / "stderr.txt").read_text() == "diagnostic\n"
assert (output / "transcripts").is_dir()
assert (output / "proxy.log").is_file()
```

The assertions pass and the output files remain after the call.
