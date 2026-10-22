# botbox: async only

## Summary

`Botbox` is async. The sync `Botbox` and `Session` are gone, and `AsyncBotbox` and `AsyncSession` take their names. botbox runs the `docker` CLI itself, so python-on-whales is no longer a dependency. The full guide is [Migrating a consumer to async botbox](../internals/async-migration.md).

## Required changes

`build()` and `run()` are awaited, and `Botbox` and `session()` are entered with `async with`:

```python
# before
with Botbox(agent, dockerfile=DOCKERFILE) as box:
    result = box.run(command, mounts=mounts, workdir="/target")

# after
async with Botbox(agent, dockerfile=DOCKERFILE) as box:
    result = await box.run(command, mounts=mounts, workdir="/target")
```

A session has no `close()`. Leaving the block ends it and sets `live.result`:

```python
# before
with box.session(mounts=mounts) as live:
    events = live.message(text)
    result = live.close()

# after
async with box.session(mounts=mounts) as live:
    events = await live.message(text)
result = live.result
```

From sync code, put one `asyncio.run(...)` at the entry point:

```python
def port(agent: Agent) -> RunResult:
    return asyncio.run(Botbox(agent).run(agent.command("Fix the tests")))


async def ask(agent: Agent, text: str) -> RunResult | None:
    async with Botbox(agent).session() as live:
        await live.message(text)
    return live.result


result = asyncio.run(ask(agent, "Fix the tests"))
```

`botbox.DockerException` is botbox's own class, `DockerException(docker_command, return_code, stderr)`, with `stderr` as `str`. It is no longer python_on_whales' class, so `except python_on_whales.exceptions.DockerException` stops catching it. Catch `botbox.DockerException`. If your own code imports `python_on_whales`, declare it as your own dependency.

Tests that patch `python_on_whales.docker.*` no longer reach botbox. Patch `Botbox` at your own module instead.

### ports

- `port_codebase()` becomes `async def` and awaits `box.run(...)` inside `async with Botbox(...)`. `run_gbnf_experiment` awaits it, or calls it through `asyncio.run(...)` at the CLI.
- `gbnf_experiment` already declares `python-on-whales` for its own Docker calls. Keep it.
- Raise the pin to `botbox>=0.1,<0.2`.

### surprisals

- `prompt_t` becomes `async with box.session(...) as t_session`, `await t_session.message(advice)`, then `result = t_session.result` after the block in place of `t_session.close()`.
- `USession.pi_session` is still typed `Session`; it is now the async one, so its callers await `message()`.
- `UAgent.turn_ended` still runs once per event, but `on_event` can move to `async for event in live.stream(text)`. A slow `on_event` now stalls the event loop.
- Fakes in the tests need `async def message`, `__aenter__` and `__aexit__`, and a `result` attribute in place of `close()`.
- Raise the pin to `botbox>=0.1,<0.2`.

## Deprecations removed

None.

## Behavior changes without code changes

- A missing image, or any container that never started, raises `DockerException` with `return_code` 125. The sync `run()` returned a `RunResult` with exit 125.
- A Docker client that dies while the daemon is up raises `DockerException`.
- A teardown step that fails after the command ran, a container removal that takes longer than 30 seconds, and a proxy log that can't be read are `RuntimeWarning`s. The result still comes back.
- Containers no longer run with `--rm`. The run reads the exit code from the stopped container, then removes it. Both containers carry the label `botbox.run=<token>`, so an owner killed with SIGKILL leaves them stopped and findable.
- Cancelling a run or session, or an `asyncio.timeout` firing, tears it down and propagates the cancel. No `RunResult` comes back.
- Inside `async with Botbox(...)`, SIGTERM cancels the task that entered the block, then the block raises `SystemExit(143)`.
- Installing botbox no longer pulls in python-on-whales.

## Verification

```python
import asyncio
import inspect

import botbox
from botbox import Botbox, ClaudeAgent

print(hasattr(botbox, "AsyncBotbox"), inspect.iscoroutinefunction(Botbox.run))
print(asyncio.run(Botbox(ClaudeAgent()).run("exit 3")).exit_code)
```

```sh
docker ps -a --filter label=botbox.run -q
```

Expected: `False True`, then `3`, then no container ids.
