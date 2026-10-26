# Claude Code

`ClaudeAgent` runs Anthropic's Claude Code CLI.

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
async with Botbox(agent) as box:
    result = await box.run(agent.command("Fix the tests"), output="runs/fix")
```

## Credentials

By default, the run uses your Claude Code login from `~/.claude/.credentials.json`. Pass `api_key` to use an API key instead. Runs that may last longer than a login token should use `api_key` (see [Login Expiry](../explanation/#login-expiry)).

With `output`, `transcripts/` there is mounted over `~/.claude/projects`. The staged credentials sit outside it.

## Sessions

`ClaudeAgent` has a session mode. See [Holding a session](../guide/holding-a-session).

What runs in the container: [How It Works](../explanation/#claude-code).
