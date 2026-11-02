**Added**: `Agent.command(prompt, resume=True)` continues the latest session, and
`Agent.command(prompt, resume="<session-id>")` resumes a specific one. Claude, pi, and Codex
implement both forms using sessions seeded through `output/transcripts/`.
