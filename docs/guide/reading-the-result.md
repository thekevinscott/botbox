---
diataxis: how-to
---

# Reading the result

`run()` returns a `RunResult` with `stdout`, `stderr`, `exit_code`, `transcript`, `proxy`, `container`, and `image`. Nothing is parsed.

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

`result.proxy` is a `str`: every connection, admitted or refused.

```python
print(result.proxy)
```

## Inspect the container

The exited container is kept. `result.container` is its id; `docker diff` lists what the run wrote outside the mounts. Remove it when done.

```python
subprocess.run(["docker", "diff", result.container])
subprocess.run(["docker", "rm", result.container])
```

Next: the [Reference](../reference/#runresult) for every field, or [the error model](../explanation/#the-error-model).
