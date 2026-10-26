Removed: **BREAKING** Python `RunResult.proxy` is gone, from `run()`, `live.result` and
`Timeout.result` alike. botbox no longer reads the proxy log back into Python: pass `output`
and read `proxy.log` there. Without `output`, the log is deleted with the temporary home, and
the "could not read its proxy log" warning is gone. See
[the migration](../migrations.d/2026-10-26-python-result-proxy.md).
