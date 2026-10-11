# botbox: `run()` keeps the container

## Summary

A completed `run()` leaves its exited container in place so it can be inspected later. `RunResult.container` is its id; `RunResult.image` is the tag that ran.

## Required changes

Remove the container when done with it:

```python
result = box.run(command)
subprocess.run(["docker", "rm", result.container])
```

## Deprecations removed

None.

## Behavior changes without code changes

Exited agent containers accumulate until removed. A run that raises still removes its container.

## Verification

```sh
docker container inspect --format '{{.State.Status}}' <result.container>
```

Expected: `exited`.
