# Claude Code

`ClaudeAgent` runs Anthropic's Claude Code CLI.

## Usage

```python
ClaudeAgent(model: str | None = None, effort: str | None = None, *, api_key: str | None = None)
```

| Option    | Default        | Meaning                                       |
| --------- | -------------- | --------------------------------------------- |
| `model`   | the CLI's own  | passed as `--model`                           |
| `effort`  | the CLI's own  | passed as `--effort`                          |
| `api_key` | `None`         | an Anthropic API key, instead of the host login |

```python
agent = ClaudeAgent(model="claude-opus-5", effort="high")
with Botbox(agent) as box:
    result = box.run(agent.command("Fix the tests"))
```

### Credentials

By default, the run uses your Claude Code login from `~/.claude/.credentials.json`. Pass `api_key` to use an API key instead. Runs that may last longer than a login token should use `api_key` (see [Login Expiry](#login-expiry)).

### Sessions

`ClaudeAgent` has a session mode. See [Holding a session](../guide/holding-a-session).

## How It Works

### Image

`agents/claude/Dockerfile`: Node, `git`, `ca-certificates` and a pinned `@anthropic-ai/claude-code`. The CLI's auto-updater and non-essential traffic are turned off.

### Command

`agent.command(prompt)` renders:

```sh
claude -p <prompt> --output-format json --dangerously-skip-permissions --strict-mcp-config
```

plus `--model` and `--effort` when set. The prompt is shell-quoted. `run()` takes any string, so you can run something else in the same image.

A session runs `claude -p --input-format stream-json --output-format stream-json --verbose` with the same permission and MCP flags. Each message goes in as a `user` event, and a turn ends at the `result` event.

### Home

The home is `/home/user`. By default `.credentials.json` is copied into `.claude/`. A copy, so a token refresh inside the run doesn't touch the host file. With `api_key`, the key goes in `.claude/api_key` (mode 600), with a `settings.json` whose `apiKeyHelper` reads it.

### Network

The proxy admits `api.anthropic.com`, plus any hosts in `allow`.

### Transcript

`result.transcript` holds every `.claude/projects/**/*.jsonl` file under the home.

### Login Expiry

A copied login is a snapshot. Its access token expires, typically within hours. Renewing it needs a host outside the allowlist (`platform.claude.com`), so the agent can't renew it inside the box, and a run that outlasts the token fails with a 401. Renewals on the host don't reach a running container.

botbox doesn't cover this. Opening the renewal host isn't a fix: renewal likely rotates the login, which would sign out the host's own sessions.
