**Changed (BREAKING):** Python `Botbox.session()` requires the keyword `output`. Omitting it
raises `TypeError`. The CLI's stdout and stderr always go to files in `output`. See
[the migration](../migrations.d/2026-10-26-python-session-output-required.md).
