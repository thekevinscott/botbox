**Added**: `PiAgent(api_key=...)` authenticates pi with an API key instead of `~/.pi/agent`: the run's temporary home gets a fresh `auth.json` (mode 600) holding only that provider's key, and no host files are read.

**Changed**: `PiAgent` copies `~/.pi/agent/models.json` only when it exists. A host home without it no longer fails with `FileNotFoundError`.
