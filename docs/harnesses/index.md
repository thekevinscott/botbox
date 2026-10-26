# Harnesses

A harness is the agent CLI botbox runs in the container. botbox ships three. Pass one to `Botbox`:

```python
from botbox import Botbox, ClaudeAgent

box = Botbox(ClaudeAgent(model="claude-opus-5", effort="high"))
```

| Harness                    | Class         | Sessions | Own hosts                                       |
| -------------------------- | ------------- | -------- | ----------------------------------------------- |
| [Claude Code](./claude)    | `ClaudeAgent` | yes      | `api.anthropic.com` with `api_key`; none on a login |
| [Codex](./codex)           | `CodexAgent`  | no       | `chatgpt.com`, or `api.openai.com` with `api_key` |
| [pi](./pi)                 | `PiAgent`     | yes      | set by `provider`                               |

Each harness logs in with your host login by default, or with an `api_key` you pass. botbox reads no `.env`: pass the key yourself.
