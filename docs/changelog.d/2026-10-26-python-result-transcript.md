Removed: **BREAKING** Python `RunResult.transcript` is gone, from `run()`, `live.result` and
`Timeout.result` alike. botbox no longer reads transcripts back into Python: pass `output`
and read `transcripts/` there. Without `output`, transcripts are deleted with the temporary
home. See [the migration](../migrations.d/2026-10-26-python-result-transcript.md).
