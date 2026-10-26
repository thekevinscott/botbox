Fixed: Python `Botbox.run()` and `Botbox.session()` no longer drop output the agent wrote just
before a cancel, timeout or failed write. Everything the Docker client printed before it was
killed now reaches `stdout.txt` and `stderr.txt`.
