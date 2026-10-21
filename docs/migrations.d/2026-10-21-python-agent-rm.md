# botbox: agent containers remove themselves

## Summary

Agent containers run with `--rm` and are gone once the run or session ends, so `RunResult` no longer carries a `container` id. This reverses the [keep-container](2026-10-11-python-keep-container.md) change: a kept container is one an owner killed with SIGKILL can't clean up.

## Required changes

Drop `container` wherever a `RunResult` is built or read. It was the sixth positional field; `image` moves up to sixth.

```python
# before
RunResult("out", "", 0, {}, "", "a-container", "an-image")
# after
RunResult("out", "", 0, {}, "", "an-image")
```

Remove any `docker rm result.container` cleanup. Code that turns a result into a dict, such as `dataclasses.asdict(result)`, no longer gets a `container` key.

To keep files the command writes, write them to a mount. There is no container left for `docker diff` or `docker cp`.

## Deprecations removed

None.

## Behavior changes without code changes

- `with Botbox(...)` removes nothing on exit. It still turns SIGTERM inside the block into `SystemExit`.
- After SIGKILL of the owner, no agent container is left, exited or running.
- If the Docker daemon dies mid-run, `stderr` ends with the Docker client's error. `exit_code` is still -1.
- A container the daemon can't create or start (a missing image, an OCI runtime error) comes back as a `RunResult` with the Docker client's exit code (125, 126 or 127) and the daemon's error in `stderr`, rather than raising `DockerException`.
- A session still open when its `with Botbox(...)` block exits is no longer force-removed. It ends when you close it or when your process exits.

## Verification

```python
from botbox import Botbox, ClaudeAgent

result = Botbox(ClaudeAgent()).run("exit 3")
print(result.exit_code, hasattr(result, "container"))
```

```sh
docker ps -a --filter name=botbox-agent- -q
```

Expected: `3 False`, then no container ids.
