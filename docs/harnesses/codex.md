# Codex

`CodexAgent` runs OpenAI's Codex CLI.

## Usage

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
with Botbox(agent) as box:
    result = box.run(agent.command("Fix the tests"))
```

### Credentials

By default, the run uses your Codex login from `~/.codex/auth.json`. Pass `api_key` to use an API key instead. The choice also sets which host the proxy admits.

### Sessions

`CodexAgent` has no session mode, and `session()` raises `NotImplementedError`. To hold a session with a Codex model, run it through pi on OpenRouter: `PiAgent("openrouter", "openai/<model>")`.

## How It Works

### Image

`agents/codex/Dockerfile`: Node, `git`, `ca-certificates` and a pinned `@openai/codex`.

### Command

`agent.command(prompt)` renders:

```sh
codex exec --json --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check --disable plugins --config analytics.enabled=false <prompt>
```

plus `--model` and `--config model_reasoning_effort=` when set. The prompt is shell-quoted. Codex's own sandbox is off because the container is the sandbox.

### Home

The home is `/home/user`. By default `auth.json` is copied into `.codex/`. With `api_key`, a fresh `.codex/auth.json` (mode 600) holds the key in API-key mode.

### Network

The proxy admits `chatgpt.com` for a host login, or `api.openai.com` with `api_key`, plus any hosts in `allow`.

### Transcript

`result.transcript` holds every `.codex/sessions/**/*.jsonl` file under the home.
