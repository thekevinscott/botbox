Fixed: a Python session no longer keeps every byte its agent prints. It drops each line once read, so `stream()` holds only the line it is reading, and it stops reading the agent while 1 MiB waits unread. A long pi turn, whose updates repeat the whole message so far, ran the host process out of memory before. A line over 1 GiB now ends the session with the new `botbox.OutputLimitExceeded`.

**BREAKING**: a session's `RunResult.stdout` keeps only the lines that aren't events, the last 1 MiB of them. See the [migration](../migrations.d/2026-10-22-python-session-retention.md).
