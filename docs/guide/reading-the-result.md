# Reading the result

`run()` returns a `RunResult` with `stdout`, `stderr`, `exit_code`, `image`, and `files`, a temp directory holding the transcript and the proxy log. Nothing is parsed.

## Check the exit code

A non-zero exit is a normal `RunResult`, not an exception. API errors inside the container show up in `exit_code` and `stderr`.

```python
if result.exit_code != 0:
    print(result.stderr)
```

## Read the transcript

`result.transcript` is a directory. Each transcript file sits at its path relative to the agent's home.

```python
for path in result.transcript.rglob("*.jsonl"):
    print(path.relative_to(result.transcript), path.stat().st_size)
```

## Read the proxy log

`result.proxy` is the path to the proxy's log: every connection, admitted or refused.

```python
print(result.proxy.read_text())
```

## Keep the files

`result.files` is deleted when the result is garbage collected. A path into it is only good while you hold the result. Copy what you want to keep:

```python
result.save("runs/fix-tests")
```

To delete the files sooner, call `result.cleanup()`, or use the result as a context manager:

```python
with await box.run(command) as result:
    print(result.proxy.read_text())
```

## Keep what the run wrote

The container is removed once its exit code is read, along with anything written outside the mounts and the agent's home. To keep a file, have the command write it to a mount.

```python
await box.run(agent.command("Write a report to /out"), mounts=[(out, "/out", "rw")], workdir="/out")
```

Next: the [`RunResult` page](../api/run-result) for every field, or [how a run works](../explanation/#a-run).
