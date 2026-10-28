# pi

`PiAgent` runs the pi coding agent against a model provider: one of pi's built-ins, or one you define in `~/.pi/agent/models.json`.

```python
PiAgent(
    provider: str,
    model: str | None = None,
    *,
    api_key: str | None = None,
    tool_timeout: float = 0,
)
```

| Option         | Default       | Meaning                                                  |
| -------------- | ------------- | -------------------------------------------------------- |
| `provider`     | required      | passed as `--provider`, with `model` only                |
| `model`        | the CLI's own | passed as `--model`                                      |
| `api_key`      | `None`        | a key for `provider`, instead of the host login          |
| `tool_timeout` | `0`, no limit | seconds per bash call; see [Tool timeout](#tool-timeout) |

`provider` comes first because it decides which host the proxy admits. pi takes `--provider` only with `--model`, so with no `model` pi picks its own default model, which may belong to another provider in `auth.json`.

```python
agent = PiAgent("openrouter", "qwen/qwen3-coder")
async with Botbox(agent) as box:
    result = await box.run(agent.command("Fix the tests"), output="runs/fix")
```

## Providers

- `openrouter`: OpenRouter, reached through the credential proxy. The CONNECT proxy admits no host for it.
- Any other name: a provider defined in `~/.pi/agent/models.json`. The proxy admits the host of the selected model's `baseUrl`, or the provider's if the model sets none. With no `model`, it admits every host the provider's models use. If the provider isn't there, or no `baseUrl` has a host, `PiAgent` raises `ValueError`. `models.json` may carry comments and trailing commas, as pi allows. With `api_key` no `models.json` is staged, so only `openrouter` works.

## Credentials

On `openrouter`, the key stays on the host. By default it is the `openrouter` key in `~/.pi/agent/auth.json`, read on the host; pass `api_key` to use another. The box gets a placeholder key, and a `models.json` holding only `openrouter`, from the host's `models.json` if it has one, with its `apiKey` and `headers` dropped, each model's `headers` dropped, and its `baseUrl` at the credential proxy. A model there that sets its own `baseUrl` raises `ValueError` when the run starts, since it would go around the proxy. The proxy adds `Authorization: Bearer <key>` to `POST /api/v1/chat/completions` and refuses every other path, so the box can't read the key's metadata or balance. The key must be a literal. One that is a `!command` or an env var name raises `ValueError` when the run starts.

For any other provider, botbox copies `~/.pi/agent/auth.json` into the box, and `models.json` beside it if it exists. That copy holds every provider's key.

With `output`, `transcripts/` there is mounted over `~/.pi/agent/sessions`. The staged credentials sit outside it.

## Sessions

`PiAgent` has a session mode. See [Holding a session](../guide/holding-a-session).

## Tool timeout

pi's bash tool has no timeout unless the model asks for one. `tool_timeout` caps every bash call at that many seconds, whatever the model asks for. A call that runs out has its process tree killed, and the model gets "Command timed out after N seconds" and carries on. botbox does this with a pi extension baked into the image, loaded with `-e` only when `tool_timeout` is set.

What runs in the container: [How It Works](../explanation/#pi).
