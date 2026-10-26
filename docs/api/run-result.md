# `RunResult`

How a run or session ended.

| Field       | What it is                                                                 |
| ----------- | -------------------------------------------------------------------------- |
| `exit_code` | The command's exit code, or -1 when none came back. |

The streams, proxy log and transcripts are files in the run's [`output`](./run) directory. Without `output`, the streams, proxy log and transcripts are deleted after the run or session.

The container is removed once its exit code is read; what it wrote outside the mounts and the agent's home goes with it. If the Docker daemon goes away mid-run, [`run()`](./run) returns with `exit_code` -1. A [`Timeout`](./botbox#timeout) holds a `RunResult` with `exit_code` -1.
