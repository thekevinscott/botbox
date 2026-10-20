---
diataxis: reference
---

# Reference

The Python API: `Botbox`, `run()`, `RunResult`, `build()`, and the agents.

## `Botbox`

```python
Botbox(agent: Agent, *, dockerfile: str | Path | None = None, allow: Sequence[str] = ())
```

| Argument     | What it is                                                     |
| ------------ | -------------------------------------------------------------- |
| `agent`      | Which agent. See [Agents](#agents).                            |
| `dockerfile` | Your layer on top of the agent's image. Build context is the Dockerfile's directory. Must end as `USER user` and leave the agent's home where it is. |
| `allow`      | Hostnames the proxy admits, in addition to the agent's own.    |

`Botbox` is a context manager. On exit from `with Botbox(...) as box:`, every container its runs created is removed, whether the block finished, raised, or was interrupted. A removal failure raises after a clean block; after a failed one, the block's exception propagates instead.

## `run()`

```python
box.run(
    command: str,
    *,
    mounts: Sequence[tuple[str | Path, str | Path, Literal["ro", "rw"]]] = (),
    workdir: str | Path | None = None,
) -> RunResult
```

| Argument  | What it is                                                              |
| --------- | ----------------------------------------------------------------------- |
| `command` | Shell command line, run as `sh -c`, passed through unchanged. No `ENTRYPOINT`. |
| `mounts`  | Bind mounts: host path, container path, mode. Missing host paths raise. |
| `workdir` | Where the command starts. Must be a mounted path or inside one; otherwise `run()` raises. Defaults to the agent's home. |

Returns a [`RunResult`](#runresult). A non-zero exit is a normal `RunResult`. Raises only when setup fails or the run is interrupted. A Docker failure during setup raises `botbox.DockerException` (python-on-whales' own class, re-exported).

## `RunResult`

Nothing parsed.

| Field       | What it is                                                           |
| ----------- | -------------------------------------------------------------------- |
| `stdout`    | The command's standard output.                                       |
| `stderr`    | The command's standard error.                                        |
| `exit_code` | The command's exit code.                                             |
| `transcript`| `dict[str, str]`: path relative to the agent's home → file contents. |
| `proxy`     | `str`: the proxy log. Every connection, admitted or refused.         |
| `container` | `str`: the id of the exited container. Yours to remove, or removed when the `with` block exits. |
| `image`     | `str`: the tag that ran: your layer's when `dockerfile` is given, else the agent's. |

The container is kept, exited, until you remove it with `docker rm <id>` or the box's `with` block exits. The agent's home (`/home/user`) was a temporary mount and is gone, so the container holds only writes outside the mounts; `docker diff <id>` lists them. A run that raises removes its container.

## `build()`

```python
box.build() -> str
```

Builds the agent's image, then your `dockerfile` on top, and returns the tag. `run()` calls this every time.

Concurrent builds of one tag, from any process, take turns.

## Agents

| Agent       | Class         | Dockerfile                 | Status     |
| ----------- | ------------- | -------------------------- | ---------- |
| Claude Code | `ClaudeAgent` | `agents/claude/Dockerfile` | supported  |
| pi          | `PiAgent`     | `agents/pi/Dockerfile`     | image only |

Agent images contain the CLI, its runtime, `git`, and `ca-certificates`. The pi image adds `python3`, `ripgrep`, and `fd`.

### Constructors

```python
ClaudeAgent(model: str | None = None, effort: str | None = None, *, api_key: str | None = None)
PiAgent(provider: str, model: str | None = None, *, api_key: str | None = None)
```

`PiAgent` requires `provider` first because it selects the egress allowlist.

| Agent         | Credentials                                                         | Own hosts           |
| ------------- | ------------------------------------------------------------------- | ------------------- |
| `ClaudeAgent` | `~/.claude/.credentials.json`, or `api_key` through `apiKeyHelper` | `api.anthropic.com` |
| `PiAgent`     | `~/.pi/agent/auth.json` (and `models.json` if present), or `api_key` in a fresh `auth.json` | `openrouter.ai` for `openrouter`; `$PI_AGENT_HOST` for `tower` |

### `command()`

```python
agent.command(prompt: str) -> str
```

Renders the agent's CLI invocation for a prompt: `claude -p <prompt> --output-format json --dangerously-skip-permissions --strict-mcp-config`, plus `--model` and `--effort` when set. The prompt is shell-quoted. `run()` still takes any string; `command()` is the agent's.

```python
agent = ClaudeAgent(model="claude-opus-5", effort="high")
box.run(agent.command("Fix the tests"))
```

See also: [How-to Guides](../guide/), [Explanation](../explanation/).
