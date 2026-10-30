# `RunResult`

How a run ended.

| Field       | What it is                                                                 |
| ----------- | -------------------------------------------------------------------------- |
| `exit_code` | The command's exit code, or -1 when none came back. |
| `oom_killed` | Whether the kernel killed a process in the agent container, the agent or a child, for running out of memory. Read from Docker's `State.OOMKilled`. `None` when botbox read no record, as after a timeout. |

The streams, proxy log and transcripts are files in the run's [`output`](./run) directory. Without `output`, the streams, proxy log and transcripts are deleted after the run.

The container is removed once its exit code is read; what it wrote outside the mounts and the agent's home goes with it. If the Docker daemon goes away mid-run, [`run()`](./run) raises `DockerException`. A [`Timeout`](./botbox#timeout) holds a `RunResult` with `exit_code` -1 and `oom_killed` `None`.
