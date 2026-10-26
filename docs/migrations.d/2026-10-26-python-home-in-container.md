# botbox: the agent's home is in its container

## Summary

A run no longer makes a host directory for the agent's home and mounts it. The home is part
of the agent container. `Agent.stage_auth` writes its files into a `HomeFiles` instead of a
host `Path`.

## Required changes

A custom agent that overrides `stage_auth` writes through `HomeFiles`:

```python
# before
def stage_auth(self, home: Path) -> None:
    target = home / ".tool" / "auth.json"
    target.parent.mkdir(parents=True)
    target.write_text(token)
    target.chmod(0o600)

# after
def stage_auth(self, home: HomeFiles) -> None:
    home.write(".tool/auth.json", token, mode=0o600)
```

Paths are relative to the home. Parent directories are made for you. A custom `dockerfile`
whose agent writes under its home must make that home writable by the host's uid, as the
harness images do.

## Deprecations removed

None. `stage_auth(home: Path)` is replaced without a deprecation period.

## Behavior changes without code changes

- No `botbox-<token>-*/home` on the host. The temp directory holds only streams and logs.
- Without `output`, transcripts go with the container.
- Mounting your own directory at the harness's home no longer collides with botbox's mount.
- The agent container's stdin carries the staged files first, as a gzipped tar. A run's command still gets no other input on it.

## Verification

```python
import asyncio
from pathlib import Path

from botbox import Botbox, ClaudeAgent

output = Path("/tmp/botbox-check")
asyncio.run(Botbox(ClaudeAgent(api_key="sk-ant-api03-x")).run("ls -a ~/.claude", output=output))
print((output / "stdout.txt").read_text())
```

Expected: the listing includes `api_key` and `settings.json`.
