# Codex

`CodexAgent` runs OpenAI's Codex CLI.

```python
CodexAgent(
    model: str | None = None,
    effort: str | None = None,
    *,
    api_key: str | None = None,
    tool_timeout: float = 0,
)
```

| Option         | Default       | Meaning                                       |
| -------------- | ------------- | --------------------------------------------- |
| `model`        | the CLI's own | passed as `--model`                           |
| `effort`       | the CLI's own | passed as `--config model_reasoning_effort=`  |
| `api_key`      | `None`        | an OpenAI API key, instead of the host login  |
| `tool_timeout` | `0`           | must be 0; see [Tool timeout](#tool-timeout)  |

```python
agent = CodexAgent("gpt-5.5", "low")
async with Botbox(agent) as box:
    result = await box.run(agent.command("Fix the tests"), output="runs/fix")
```

## Credentials

By default, the run uses your Codex login from `~/.codex/auth.json`. Pass `api_key` to use an API key instead. Either way the credential stays on the host: the box gets a placeholder, and a credential proxy adds the real token or key to Codex's requests. If the login has already expired, `run()` raises `CredentialsExpired`; run `codex` on the host to renew it.

With `output`, `transcripts/` there is mounted over `~/.codex/sessions`. The staged credentials sit outside it.

## Tool timeout

Codex has no setting that kills a shell command after a time limit, so `tool_timeout` above 0 raises `NotImplementedError` when the agent is created. Its shell tool returns to the model after at most 30 seconds and leaves a long command running in the background, so a slow command does not block the model. The command keeps running until Codex exits. To bound a whole run, use the `timeout` on `Botbox`.

What runs in the container: [How It Works](../explanation/#codex).
