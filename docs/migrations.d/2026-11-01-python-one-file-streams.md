## Summary

Run streams and the proxy log now each have one destination. Docker receives the open file directly, avoiding Python output sinks and duplicate scratch copies when `output` is supplied.

## Required changes

None for normal output paths. If a caller relied on botbox warning and continuing after an output file stopped accepting writes, handle the resulting `DockerException` instead.

## Deprecations removed

None.

## Behavior changes without code changes

With `output`, stdout, stderr, and the proxy log are no longer copied into scratch. A destination that fails during a run, such as `/dev/full`, fails the attached Docker client and the run instead of being dropped with a warning.

## Verification

Run `Botbox.run("echo ready", output=path)` with a writable directory. `path/stdout.txt` contains `ready\n`; `path/stderr.txt` and `path/proxy.log` are available during the run. Reuse the directory to confirm the three files are truncated for each run.
