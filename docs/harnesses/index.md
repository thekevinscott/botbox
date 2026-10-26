# Harnesses

A harness is the agent CLI botbox runs in the container. botbox ships three. Pass one to `Botbox`:

```python
from botbox import Botbox, ClaudeAgent

box = Botbox(ClaudeAgent(model="claude-opus-5", effort="high"))
```

| Harness                    | Class         | Sessions | Own hosts                                       |
| -------------------------- | ------------- | -------- | ----------------------------------------------- |
| [Claude Code](./claude)    | `ClaudeAgent` | yes      | `api.anthropic.com` with `api_key`; none on a login |
| [Codex](./codex)           | `CodexAgent`  | no       | none                                            |
| [pi](./pi)                 | `PiAgent`     | yes      | none on `openrouter`; else set by `provider`    |

Each harness logs in with your host login by default, or with an `api_key` you pass. Claude Code's and Codex's logins and `api_key`s, and pi's OpenRouter key, stay on the host, and a credential proxy adds them to the CLI's requests. pi's custom providers are copied into the run's home. botbox reads no `.env`: pass the key yourself.
