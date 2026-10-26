# Claude Code

`ClaudeAgent` runs Anthropic's Claude Code CLI.

```python
ClaudeAgent(
    model: str | None = None,
    effort: str | None = None,
    *,
    api_key: str | None = None,
    tool_timeout: float = 0,
)
```

| Option         | Default       | Meaning                                          |
| -------------- | ------------- | ------------------------------------------------ |
| `model`        | the CLI's own | passed as `--model`                              |
| `effort`       | the CLI's own | passed as `--effort`                             |
| `api_key`      | `None`        | an Anthropic API key, instead of the host login  |
| `tool_timeout` | `0`, no limit | seconds per Bash call; see [Tool timeout](#tool-timeout) |

```python
agent = ClaudeAgent(model="claude-opus-5", effort="high")
async with Botbox(agent) as box:
    result = await box.run(agent.command("Fix the tests"), output="runs/fix")
```

## Credentials

By default, the run uses your Claude Code login from `~/.claude/.credentials.json`. Pass `api_key` to use an API key instead. Runs that may last longer than a login token should use `api_key` (see [Login Expiry](../explanation/#login-expiry)).

With `output`, `transcripts/` there is mounted over `~/.claude/projects`. The staged credentials sit outside it.

## Sessions

`ClaudeAgent` has a session mode. See [Holding a session](../guide/holding-a-session).

## Tool timeout

`tool_timeout` caps every Bash call at that many seconds, whatever timeout the model asks for. A call that runs out is killed, and the model gets "Command timed out" and carries on. `command()` and `session_command()` set `BASH_DEFAULT_TIMEOUT_MS` and `BASH_MAX_TIMEOUT_MS` on the CLI's command, plus `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, so only the CLI sees them. They are in `agent.env`. Without that last one, Claude Code moves a timed-out command to the background and leaves it running. So with a `tool_timeout`, the agent can't use `run_in_background`.

Grep and Glob already stop after 20 seconds on their own.

What runs in the container: [How It Works](../explanation/#claude-code).
