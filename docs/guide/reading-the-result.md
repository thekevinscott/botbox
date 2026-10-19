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

The exited container is kept. `result.container` is its id; `docker diff` lists what the run wrote outside the mounts.

Open the box with `with` and every container its runs created is removed when the block exits, including on an exception or Ctrl-C. Inspect inside the block. The rest of the result is plain data and stays readable after.

```python
with Botbox(agent) as box:
    result = box.run(agent.command("Fix the tests"))
    subprocess.run(["docker", "diff", result.container])
print(result.stdout)
```

To keep a container for debugging, use the box without `with` and remove it yourself when done.

```python
result = box.run(agent.command("Fix the tests"))
subprocess.run(["docker", "rm", result.container])
```

Next: the [Reference](../reference/#runresult) for every field, or [the error model](../explanation/#the-error-model).
