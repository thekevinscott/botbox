# pi

`PiAgent` runs the pi coding agent against a model provider: one of pi's built-ins, or one you define in `~/.pi/agent/models.json`.

```python
PiAgent(provider: str, model: str | None = None, *, api_key: str | None = None)
```

| Option     | Default       | Meaning                                         |
| ---------- | ------------- | ----------------------------------------------- |
| `provider` | required      | passed as `--provider`                          |
| `model`    | the CLI's own | passed as `--model`                             |
| `api_key`  | `None`        | a key for `provider`, instead of the host login |

`provider` comes first because it decides which host the proxy admits.

```python
agent = PiAgent("openrouter", "qwen/qwen3-coder")
async with Botbox(agent) as box:
    result = await box.run(agent.command("Fix the tests"))
```

## Providers

- `openrouter`: OpenRouter. The proxy admits `openrouter.ai`.
- Any other name: a provider defined in `~/.pi/agent/models.json`. The proxy admits the host of its `baseUrl`. If the provider isn't there, or has no `baseUrl`, `PiAgent` raises `ValueError`. With `api_key` no `models.json` is staged, so only `openrouter` works.

## Credentials

By default, the run uses your pi login from `~/.pi/agent/auth.json`, and `models.json` beside it if it exists. Pass `api_key` to use a key for `provider` instead.

## Sessions

`PiAgent` has a session mode. See [Holding a session](../guide/holding-a-session).

What runs in the container: [How It Works](../explanation/#pi).
