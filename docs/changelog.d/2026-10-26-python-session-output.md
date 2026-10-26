Added: Python `Botbox.session()` accepts an optional `output` directory, as `run()` does.
With it, the CLI's stdout and stderr go directly to `stdout.txt` and `stderr.txt`, the
proxy's output to `proxy.log`, and transcripts to `transcripts/`, all kept after teardown.
Events are read by following `stdout.txt`. `live.result` holds only `exit_code` and
`image` in this mode, including in `Timeout.result`, and agent Docker errors point to the
stderr file. Sessions without `output` keep their current behavior.
