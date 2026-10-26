**Changed (BREAKING):** Python `Botbox.run()` and `Botbox.session()` require the keyword
`output`. Omitting it raises `TypeError`. stdout and stderr always go to files in
`output`; nothing is captured in Python. `Session` drops its `stdout` and `stderr`
attributes and takes a `readline` callable in place of them. See
[the migration](../migrations.d/2026-10-26-python-output-required.md).
