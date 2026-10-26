# `RunResult`

Nothing parsed.

When [`run(output=...)`](./run) or [`session(output=...)`](./session) is used, `stdout`,
`stderr` and `proxy` are empty strings; read `stdout.txt`, `stderr.txt` and `proxy.log` in
that directory instead. `exit_code` and `image` are unchanged. Transcripts are only kept in
`output/transcripts/`; without `output` they are deleted with the temporary home.

| Field       | What it is                                                           |
| ----------- | -------------------------------------------------------------------- |
| `stdout`    | The command's standard output.                                       |
| `stderr`    | The command's standard error.                                        |
| `exit_code` | The command's exit code.                                             |
| `proxy`     | `str`: the proxy log. Every connection, admitted or refused.         |
| `image`     | `str`: the tag that ran: your layer's when `dockerfile` is given, else the agent's. |

The container is removed once its exit code is read; what it wrote outside the mounts and the agent's home goes with it. If the Docker daemon goes away mid-run, [`run()`](./run) returns what arrived, with `exit_code` -1. A [`Timeout`](./botbox#timeout) holds what arrived the same way.
