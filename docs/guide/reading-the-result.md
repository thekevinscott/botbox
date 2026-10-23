# Reading the result

`run()` returns a `RunResult` with `stdout`, `stderr`, `exit_code`, `transcript`, `proxy`, `image`, and `truncated`. Nothing is parsed. `truncated` is `True` when `stdout` or `stderr` passed its [cap](../api/botbox#output-caps) and only its end was kept.

## Check the exit code

A non-zero exit is a normal `RunResult`, not an exception. API errors inside the container show up in `exit_code` and `stderr`.

```python
if result.exit_code != 0:
    print(result.stderr)
```

## Read the transcript

`result.transcript` is a `dict[str, str]`: path relative to the agent's home → file contents.

```python
for path, contents in result.transcript.items():
    print(path, len(contents))
```

## Read the proxy log

`result.proxy` is a `str`: every connection, admitted or refused, up to the log's last 1 MiB.

```python
print(result.proxy)
```

## Keep what the run wrote

The container is removed once its exit code is read, along with anything written outside the mounts and the agent's home. To keep a file, have the command write it to a mount.

```python
await box.run(agent.command("Write a report to /out"), mounts=[(out, "/out", "rw")], workdir="/out")
```

Next: the [`RunResult` page](../api/run-result) for every field, or [how a run works](../explanation/#a-run).
