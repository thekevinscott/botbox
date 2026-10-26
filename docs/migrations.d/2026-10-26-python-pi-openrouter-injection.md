# botbox: pi's OpenRouter key stays on the host

## Summary

A `PiAgent` on `openrouter` used to copy the host's whole `~/.pi/agent/auth.json` and
`models.json` into the box, or write the `api_key` there, so anything in the box could read
the key. Now the box gets a placeholder key and the credential proxy adds the real one to pi's
requests to `openrouter.ai`.

## Required changes

A host `auth.json` whose `openrouter` key is a `!command` or an env var name must hold the
literal key instead, or the caller passes it:

```python
# before: auth.json held {"openrouter": {"type": "api_key", "key": "!op read op://vault/or"}}
agent = PiAgent("openrouter")

# after
agent = PiAgent("openrouter", api_key=read_key_on_the_host())
```

## Deprecations removed

None.

## Behavior changes without code changes

- `PiAgent("openrouter").allow` is `()`. `openrouter.ai` is no longer on the tinyproxy allow
  list; tools in the box that call it directly are refused.
- The proxy forwards only `POST /api/v1/chat/completions`. `/api/v1/models`, `/api/v1/key`
  and the rest get a 403.
- The box's `auth.json` holds only a placeholder `openrouter` key, and its `models.json` only
  the `openrouter` provider, without `apiKey`, `headers`, or any model's `baseUrl` and
  `headers`. Keys for other providers no longer enter the box.
- Each run on `openrouter` starts the credential sidecar and writes `credentials.log` to
  `output`.
- Custom providers from `models.json` are unchanged.

## Verification

```python
import asyncio
from pathlib import Path

from botbox import Botbox, PiAgent

output = Path("/tmp/botbox-check")
agent = PiAgent("openrouter", "openai/gpt-4o-mini")
asyncio.run(Botbox(agent).run(agent.command("Reply with exactly: pong"), output=output))
print("pong" in (output / "stdout.txt").read_text())
print("POST /api/v1/chat/completions 200" in (output / "credentials.log").read_text())
```

Expected: `True`, then `True`.
