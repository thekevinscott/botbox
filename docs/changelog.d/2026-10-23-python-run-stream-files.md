Added: Python `Botbox.run()` accepts an optional `output` directory. With it, stdout
and stderr stream directly to `stdout.txt` and `stderr.txt` and remain available after
teardown. The result's stdout/stderr fields are empty in this mode, and agent Docker
errors point to the stderr file. Existing stream files are truncated; other files remain.
Calls without `output` keep their current behavior.
