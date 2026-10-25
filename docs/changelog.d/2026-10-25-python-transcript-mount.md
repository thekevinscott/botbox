Changed: Python `Botbox.run(output=...)` bind-mounts `output/transcripts/` over the
agent's sessions directory, so the CLI writes its transcripts there directly. The result's
`transcript` field is empty in this mode. botbox stages credentials outside the sessions
directory. A path containing `:` raises `ValueError` before setup. Calls without
`output` still read transcripts into the result. The `Agent` protocol's `transcripts` glob
is replaced by `sessions_dir`, a directory relative to the agent's home.
