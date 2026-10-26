**Changed (BREAKING):** Python `Botbox.run()` requires the keyword `output`. Omitting it
raises `TypeError`. stdout, stderr and the proxy log always go to files in `output`; nothing
is captured in Python. See
[the migration](../migrations.d/2026-10-26-python-run-output-required.md).
