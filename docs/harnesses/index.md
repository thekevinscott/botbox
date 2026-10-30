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

## Filtering stdout

A subclass can filter what its CLI prints before botbox writes it by defining `filter_stdout`:

```python
from botbox import ClaudeAgent

class Quiet(ClaudeAgent):
    def filter_stdout(self, line: bytes) -> bytes | None:
        return None if line.startswith(b"DEBUG ") else line
```

botbox calls it once per line of stdout, however Docker splits the output. `line` ends with its newline, except the unterminated rest the CLI leaves at exit, which is passed too. The bytes it returns are written to `stdout.txt` as they are, so keep the newline; `None` drops the line. Session events are read from what was written, so a dropped line is never an event; an unterminated last line is written but not read as an event. stderr is not filtered. Agents that don't override it have stdout written as it comes. An error raised in `filter_stdout` ends the run or session with that error, and nothing more is written.
