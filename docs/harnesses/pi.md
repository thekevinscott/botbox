# pi

`PiAgent` runs the pi coding agent against a model provider: OpenRouter, or a model host on your own network.

```python
PiAgent(provider: str, model: str | None = None, *, api_key: str | None = None)
```

| Option     | Default       | Meaning                                         |
| ---------- | ------------- | ----------------------------------------------- |
| `provider` | required      | `openrouter` or `tower`                         |
| `model`    | the CLI's own | passed as `--model`                             |
| `api_key`  | `None`        | a key for `provider`, instead of the host login |

`provider` comes first because it decides which host the proxy admits.

```python
agent = PiAgent("openrouter", "qwen/qwen3-coder")
async with Botbox(agent) as box:
    result = await box.run(agent.command("Fix the tests"))
```

## Providers

- `openrouter`: OpenRouter.
- `tower`: a model host on your own network. Set `PI_AGENT_HOST` to the host it serves from, or `PiAgent` raises `ValueError`.

## Credentials

By default, the run uses your pi login from `~/.pi/agent/auth.json`, and `models.json` beside it if it exists. Pass `api_key` to use a key for `provider` instead.

## Sessions

`PiAgent` has a session mode. See [Holding a session](../guide/holding-a-session).

What runs in the container: [How It Works](../explanation/#pi).
