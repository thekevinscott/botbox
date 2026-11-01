## Summary

Docker clients now run through posix-tools `spawn`, which kills and reaps the process group on cancellation or failure. The local `execute` wrapper and duplicate `settle` implementations have been removed.

## Required changes

Pass open writable binary files to `Image.run(stdout=..., stderr=...)` and `Container.exec(stdout=..., stderr=...)` instead of callbacks. For example, replace `stdout=chunks.extend` with `stdout=output_file`, then read the file after the call or while the client runs. `adocker.utils.execute`, `adocker.utils.Sink`, and the local `settle` modules are no longer available; use `posix_tools.spawn` and `posix_tools.settle` directly.

## Deprecations removed

None.

## Behavior changes without code changes

Callable output sinks are no longer accepted. Docker writes directly to the given stream. Cancellation and failure cleanup is delegated to posix-tools 0.0.14.

## Verification

Open two binary files and pass them as `stdout` and `stderr` to `Image("busybox").run("sh", "-c", "echo ready; echo error >&2", name="example", stdout=out, stderr=err)`, then await the returned container's `wait()`. It returns 0, `out` contains `ready\n`, and `err` contains `error\n`.
