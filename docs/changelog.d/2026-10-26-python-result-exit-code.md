Removed: **BREAKING** Python `RunResult` holds only `exit_code`. Its `stdout`, `stderr` and
`image` fields are gone, from `run()`, `live.result` and `Timeout.result` alike. Pass `output`
and read `stdout.txt` and `stderr.txt` there; the tag that ran is `await box.build()`. Without
`output`, the streams are not kept, and the "could not read its session artifacts" warning is
gone. See [the migration](../migrations.d/2026-10-26-python-result-exit-code.md).
