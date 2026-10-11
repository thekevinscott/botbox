**Fixed**: `ClaudeAgent.command()` now renders `--dangerously-skip-permissions`; without it, `claude -p` denied every tool call and wrote nothing to the mounts.
