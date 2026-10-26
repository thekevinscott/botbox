**Changed (BREAKING):** Python `Session` drops its `stdout` and `stderr` attributes, and its
constructor takes a `readline` callable in place of them. See
[the migration](../migrations.d/2026-10-26-python-session-file-only.md).
