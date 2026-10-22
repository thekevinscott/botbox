**Added**: `Botbox(stdout_limit=..., stderr_limit=...)` caps the bytes of a `run()`'s stdout and stderr held in memory. Past a cap only the end is kept, and the new `RunResult.truncated` is `True`. Both default to 100 GiB, a ceiling rather than a budget: lower them to what your runs need. A negative cap raises `ValueError`.

**Changed**: `RunResult.proxy` holds only the last 1 MiB of the proxy log.
