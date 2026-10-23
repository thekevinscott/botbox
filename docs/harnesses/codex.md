# Codex

`CodexAgent` runs OpenAI's Codex CLI.

```python
CodexAgent(model: str | None = None, effort: str | None = None, *, api_key: str | None = None)
```

| Option    | Default        | Meaning                                          |
| --------- | -------------- | ------------------------------------------------ |
| `model`   | the CLI's own  | passed as `--model`                              |
| `effort`  | the CLI's own  | passed as `--config model_reasoning_effort=`     |
| `api_key` | `None`         | an OpenAI API key, instead of the host login     |

```python
agent = CodexAgent("gpt-5.5", "low")
async with Botbox(agent) as box:
    result = await box.run(agent.command("Fix the tests"), output="output")
```

## Credentials

By default, the run uses your Codex login from `~/.codex/auth.json`. Pass `api_key` to use an API key instead. The choice also sets which host the proxy admits: `chatgpt.com` for a host login, `api.openai.com` with `api_key`.

## Sessions

`CodexAgent` has no session mode, and `session()` raises `NotImplementedError`. To hold a session with a Codex model, run it through pi on OpenRouter: `PiAgent("openrouter", "openai/<model>")`.

What runs in the container: [How It Works](../explanation/#codex).
