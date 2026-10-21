# Motivation

Running experiments with LLM agents needs a container. An experiment runs an agent many times, unattended, with its permission prompts turned off. Each run should see only the files you give it, reach only the hosts you allow, and leave a record of what it did.

botbox is that container. It gives each run five things:

1. **A pre-configured agent CLI.** Claude Code, Codex or Pi, ready to run.
2. **No capabilities, no privilege escalation.** `--cap-drop ALL`, `no-new-privileges`, no setuid binaries.
3. **Network only to an allowlist.** No network access beyond the hosts you allow.
4. **Mounted directories.** Read-only or read-write.
5. **Logs available.** The agent's transcript and the proxy's log come back on the result.

The Python SDK is the public API.

Next: [Getting Started](./getting-started).
