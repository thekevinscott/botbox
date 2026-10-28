# botbox: agents subclass `Agent`

## Summary

`Agent` was a `Protocol`, with `SessionAgent` and `InjectingAgent` beside it. It is now one abstract base class. A custom agent subclasses it; a duck-typed class no longer counts as an agent. `SessionAgent` and `InjectingAgent` are gone.

## Required changes

Before:

```python
class MyAgent:
    image = "my-agent:latest"
    dockerfile = Path("Dockerfile")
    home = "/home/user"
    sessions_dir = ".my-agent/sessions"
    allow = ("api.example.com",)

    def stage_auth(self, home: HomeFiles) -> None: ...
    def command(self, prompt: str) -> str: ...
```

After:

```python
from botbox import Agent

class MyAgent(Agent):
    ...  # same body
```

For a session mode, override `session_command`, `encode` and `turn_ended`, as before. For the credential proxy, set `credential_source`, as before. Replace `SessionAgent` and `InjectingAgent` in type hints with `Agent`. Replace `isinstance(agent, InjectingAgent)` with `agent.credential_source is not None`.

## Deprecations removed

`SessionAgent` and `InjectingAgent`, removed without a deprecation period.

## Behavior changes without code changes

`session()` on an agent with no session mode raises `NotImplementedError` from the agent's `session_command`, where it used to raise `TypeError`. It still raises before anything is built.

## Verification

Instantiate your agent. A subclass missing `stage_auth` or `command` raises `TypeError`. Then `Botbox(MyAgent()).run(...)` runs as before.
