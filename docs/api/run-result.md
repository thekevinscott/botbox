# `RunResult`

Nothing parsed. The transcript and proxy log stay on disk, in a temp directory the result owns.

| Field       | What it is                                                           |
| ----------- | -------------------------------------------------------------------- |
| `stdout`    | The command's standard output.                                       |
| `stderr`    | The command's standard error.                                        |
| `exit_code` | The command's exit code.                                             |
| `image`     | `str`: the tag that ran: your layer's when `dockerfile` is given, else the agent's. |
| `files`     | `Path`: the result's temp directory.                                 |
| `transcript`| `Path`: `files / "transcript"`. The transcript files, at their paths relative to the agent's home. |
| `proxy`     | `Path`: `files / "proxy.log"`. Every connection, admitted or refused. |

```python
result.save(dest)   # copy `files` to `dest`, which must not exist yet; returns the path
result.cleanup()    # delete `files` now
with result: ...    # delete `files` when the block ends
```

`files` is deleted when the result is garbage collected, as `tempfile.TemporaryDirectory` does. A path into it is only good while you hold the result. To keep the files, `save()` them. A process killed outright leaves the directory, `botbox-result-*` in the system temp directory.

The container is removed once its exit code is read; what it wrote outside the mounts and the agent's home goes with it. If the Docker daemon goes away mid-run, [`run()`](./run) returns what arrived, with `exit_code` -1.
