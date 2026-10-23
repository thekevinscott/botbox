# `RunResult`

Nothing parsed.

| Field       | What it is                                                           |
| ----------- | -------------------------------------------------------------------- |
| `stdout`    | The command's standard output.                                       |
| `stderr`    | The command's standard error.                                        |
| `exit_code` | The command's exit code.                                             |
| `transcript`| `dict[str, str]`: path relative to the agent's home → file contents. |
| `proxy`     | `str`: the proxy log. Every connection, admitted or refused.         |
| `image`     | `str`: the tag that ran: your layer's when `dockerfile` is given, else the agent's. |

The container is removed once its exit code is read; what it wrote outside the mounts and the agent's home goes with it. If the Docker daemon goes away mid-run, [`run()`](./run) returns what arrived, with `exit_code` -1.
