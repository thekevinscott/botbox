# botbox: Codex's login and key stay on the host

## Summary

`CodexAgent` used to copy the host's `~/.codex/auth.json` into the box, or write the API key
there, so anything in the box could read the access, refresh and id tokens or the key. Now the
box gets a placeholder `auth.json` and a `config.toml` that points Codex at the credential
proxy, and the proxy adds the real token or key to Codex's requests.

## Required changes

Code that relied on `CodexAgent().allow` admitting `chatgpt.com` or `api.openai.com` adds the
host itself:

```python
# before
Botbox(CodexAgent())  # allow held ("chatgpt.com",)

# after
Botbox(CodexAgent(), allow=["chatgpt.com"])  # only for tools that call it directly
```

Callers on the host login can catch the new error:

```python
from botbox import Botbox, CodexAgent, CredentialsExpired

try:
    await Botbox(CodexAgent()).run(command)
except CredentialsExpired:
    ...  # run `codex` on the host to refresh the login, then retry
```

## Deprecations removed

None.

## Behavior changes without code changes

- `chatgpt.com` and `api.openai.com` are no longer on the tinyproxy allow list. Codex reaches
  them only through the credential proxy, on `/backend-api/codex/(responses|models)` with a
  login and `/v1/responses` with a key. Other paths get the proxy's 403.
- `~/.codex/auth.json` in the box holds unsigned placeholder tokens with the host's account id
  and plan, or a placeholder key. `~/.codex/config.toml` selects a `botbox` model provider and
  sets `chatgpt_base_url` to the proxy. A command that is not `CodexAgent.command()` still runs
  through them.
- `CodexAgent.command()` passes `--disable apps`.
- A host `auth.json` with no ChatGPT tokens (one in API-key mode) raises `ValueError` when the
  run starts. Pass the key as `api_key` instead.
- Each Codex run starts the credential sidecar and writes `credentials.log` to `output`.

## Verification

```python
import asyncio
from pathlib import Path

from botbox import Botbox, CodexAgent

output = Path("/tmp/botbox-check")
agent = CodexAgent()
asyncio.run(Botbox(agent).run(agent.command("Reply with exactly: pong"), output=output))
print("pong" in (output / "stdout.txt").read_text())
print("POST /backend-api/codex/responses 200" in (output / "credentials.log").read_text())
```

Expected: `True`, then `True`.
