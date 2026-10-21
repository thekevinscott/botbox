# Harnesses

A harness is the agent CLI botbox runs in the container. botbox ships three. Pass one to `Botbox`:

```python
from botbox import Botbox, ClaudeAgent

box = Botbox(ClaudeAgent(model="claude-opus-5", effort="high"))
```

| Harness                    | Class         | Sessions | Own hosts                                       |
| -------------------------- | ------------- | -------- | ----------------------------------------------- |
| [Claude Code](./claude)    | `ClaudeAgent` | yes      | `api.anthropic.com`                             |
| [Codex](./codex)           | `CodexAgent`  | no       | `chatgpt.com`, or `api.openai.com` with `api_key` |
| [pi](./pi)                 | `PiAgent`     | yes      | set by `provider`                               |

Each page has two parts. Usage covers the Python API. How It Works covers what botbox does in the container: the image, the command it runs, the files it stages in the home, and where the transcript comes from.

All three log in one of two ways, never both. By default the host's login file is copied into the run's temporary home. With `api_key`, botbox writes a fresh credentials file (mode 600) holding only that key, and reads nothing from the host. botbox reads no `.env`: the caller passes the key.

## Adding a Harness

A harness is a Dockerfile plus a class that knows the home path, the credentials file, the transcript files, the hosts the CLI needs, and how to call the CLI. Each image stands alone, with no shared base. To add one: one Dockerfile, one class, one row in the table above.
