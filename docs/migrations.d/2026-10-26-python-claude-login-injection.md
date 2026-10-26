# botbox: Claude's login stays on the host

## Summary

A `ClaudeAgent` without `api_key` used to copy the host's `~/.claude/.credentials.json` into
the box, so anything in the box could read the access and refresh tokens. Now the box gets a
placeholder login and the credential proxy adds the real access token to Claude Code's
requests to `api.anthropic.com`. The refresh token never leaves the host.

## Required changes

Code that read `ClaudeAgent.allow` on the class reads it on an instance:

```python
# before
hosts = ClaudeAgent.allow

# after
hosts = ClaudeAgent().allow  # () on a login, ("api.anthropic.com",) on an API key
```

Callers that run on the host login can catch the new error:

```python
from botbox import Botbox, ClaudeAgent, CredentialsExpired

try:
    await Botbox(ClaudeAgent()).run(command)
except CredentialsExpired:
    ...  # run `claude` on the host to refresh the login, then retry
```

## Deprecations removed

None.

## Behavior changes without code changes

- On a login, `api.anthropic.com` is no longer on the tinyproxy allow list. Tools in the box
  that call it directly, rather than through `ANTHROPIC_BASE_URL`, are refused.
- `~/.claude/.credentials.json` in the box holds placeholder tokens with a far-future expiry.
- Each run on a login starts the credential sidecar and writes `credentials.log` to `output`.
- botbox never refreshes the login. It raises `CredentialsExpired` before starting if the host
  token has already expired, and otherwise sends whatever the host's file holds. A token that
  expires mid-run fails the next turn with a 401 until Claude Code on the host refreshes it.
- `ClaudeAgent(api_key=...)` is unchanged.

## Verification

```python
import asyncio
import json
from pathlib import Path

from botbox import Botbox, ClaudeAgent

output = Path("/tmp/botbox-check")
agent = ClaudeAgent()
asyncio.run(Botbox(agent).run(agent.command("Reply with exactly: pong"), output=output))
print(json.loads((output / "stdout.txt").read_text())["result"])
print("POST /v1/messages" in (output / "credentials.log").read_text())
```

Expected: `pong`, then `True`.
