# pi

`PiAgent` runs the pi coding agent against a model provider: OpenRouter, or a model host on your own network.

## Usage

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
with Botbox(agent) as box:
    result = box.run(agent.command("Fix the tests"))
```

### Providers

- `openrouter`: OpenRouter.
- `tower`: a model host on your own network. Set `PI_AGENT_HOST` to the host it serves from, or `PiAgent` raises `ValueError`.

### Credentials

By default, the run uses your pi login from `~/.pi/agent/auth.json`, and `models.json` beside it if it exists. Pass `api_key` to use a key for `provider` instead.

### Sessions

`PiAgent` has a session mode. See [Holding a session](../guide/holding-a-session).

## How It Works

### Image

`agents/pi/Dockerfile`: Node, `git`, `ca-certificates`, `python3`, `ripgrep`, `fd` and a pinned `@earendil-works/pi-coding-agent`.

### Command

`agent.command(prompt)` renders:

```sh
pi -p <prompt> --mode json --provider <provider>
```

plus `--model` when set. The prompt is shell-quoted.

A session runs `pi --mode rpc --provider <provider>`. Each message goes in as a `prompt` command, and a turn ends at the `agent_end` event.

### Home

The home is `/home/user`. By default `auth.json`, and `models.json` if present, are copied into `.pi/agent/`. With `api_key`, a fresh `.pi/agent/auth.json` (mode 600) holds the key for `provider` and nothing else, and no host files are read.

### Network

The proxy admits `openrouter.ai` for `openrouter`, or `$PI_AGENT_HOST` for `tower`, plus any hosts in `allow`.

### Transcript

`result.transcript` holds every `.pi/agent/sessions/**/*.jsonl` file under the home.
