---
diataxis: explanation
---

# Explanation

Why botbox is shaped the way it is.

## Goals

An experiment that puts an agent in a box needs five things:

1. **A pre-configured agent CLI.** Claude Code or Pi pre-configured.
2. **No capabilities, no privilege escalation.** `--cap-drop ALL`, `no-new-privileges`, no setuid binaries.
3. **Network only to an allowlist.** No network access beyond the whitelist.
4. **Mounted directories.** Read-only or read-write.
5. **Logs available.** The agent's transcript and the proxy's log come back on the result.

The Python SDK is the public API.

## The error model

A non-zero exit is a normal `RunResult`. API errors inside the container are the CLI's to handle; they show up in `exit_code` and `stderr`. If the Docker daemon dies mid-run, `run()` still returns a `RunResult` with whatever transcript and proxy log exist.

`run()` raises only when setup fails or the run is interrupted.

## Home and credentials

Each run gets a fresh temporary home, mounted at the agent's home path. After the command exits, transcript files are read into `result.transcript` and the temporary home is deleted.

`ClaudeAgent` authenticates one of two ways, never both:

- Default: `~/.claude/.credentials.json` is copied into the temporary home.
- `ClaudeAgent(api_key=key)`: the key is written to `.claude/api_key` (mode 600) in the temporary home, with a `settings.json` whose `apiKeyHelper` reads it.

`PiAgent` likewise, never both:

- Default: `~/.pi/agent/auth.json` is copied into the temporary home, and `models.json` beside it if it exists.
- `PiAgent(provider, api_key=key)`: a fresh `.pi/agent/auth.json` (mode 600) holds the key for `provider` and nothing else. No host files are read.

botbox reads no `.env` and no environment variables. The caller passes the key.

## Network

The container joins a Docker `--internal` network. The only way out is a CONNECT proxy that denies by default. The agent contributes its own hosts (`api.anthropic.com` for Claude Code); `allow` adds more.

Every connection, admitted or refused, is logged to `result.proxy`. Network and proxy are per run and removed afterwards, including on failure.

There is no network at run time beyond the allowlist, so installs happen in the image build.

## No shared base image

An agent is a Dockerfile plus a class that knows the home path, the credentials file, the transcript files, the hosts the CLI needs, and how to invoke the CLI. Each agent's image stands alone. To add an agent: one Dockerfile, one class, one row.

Apply this: [Allowing hosts](../guide/allowing-hosts), [Reading the result](../guide/reading-the-result).
