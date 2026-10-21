# How It Works

Why botbox is shaped the way it is.

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

### Known gap: subscription logins expire mid-run

A copied login is a snapshot. Its access token expires, typically within hours, and renewing it needs a host outside the allowlist (`platform.claude.com` for Claude Code), so the agent can't renew it inside the box. A run that outlasts the token fails with a 401. Renewals on the host don't reach a running container.

botbox doesn't cover this. Opening the renewal host isn't a fix: renewal likely rotates the login, which would sign out the host's own sessions. For runs that may outlast the token, pass `api_key`.

## Network

The container joins a Docker `--internal` network. The only way out is a CONNECT proxy that denies by default. The agent contributes its own hosts (`api.anthropic.com` for Claude Code); `allow` adds more.

Every connection, admitted or refused, is logged to `result.proxy`. Network and proxy are per run and removed afterwards, including on failure.

There is no network at run time beyond the allowlist, so installs happen in the image build.

## No shared base image

An agent is a Dockerfile plus a class that knows the home path, the credentials file, the transcript files, the hosts the CLI needs, and how to invoke the CLI. Each agent's image stands alone. To add an agent: one Dockerfile, one class, one row.

Apply this: [Allowing hosts](../guide/allowing-hosts), [Reading the result](../guide/reading-the-result).
