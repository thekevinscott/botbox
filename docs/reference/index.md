# Reference

The Python API: `Botbox`, `run()`, `RunResult`, `session()`, `Session`, `build()`, and the agents.

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

## `session()`

```python
box.session(
    *,
    mounts: Sequence[tuple[str | Path, str | Path, Literal["ro", "rw"]]] = (),
    workdir: str | Path | None = None,
) -> Session
```

Starts the agent's CLI in its session mode and holds it open. `mounts` and `workdir` are as for [`run()`](#run), and so are the lockdown and the temporary home. The container runs under an init process, so background processes the agent starts are reaped when the CLI exits. Raises `TypeError` for an agent with no session mode. `ClaudeAgent` runs `claude -p --input-format stream-json --output-format stream-json --verbose`, and a turn ends at its `result` event. `PiAgent` runs `pi --mode rpc`, and a turn ends at `agent_end`. `CodexAgent` raises `NotImplementedError`: its only long-running mode, `codex app-server`, needs a per-session handshake. For a Codex model in a session, use `PiAgent("openrouter", "openai/<model>")`. The container is removed when the box's `with` block exits.

## `Session`

| Member              | What it is                                                                 |
| ------------------- | -------------------------------------------------------------------------- |
| `message(text)`     | Sends `text`, blocks until the turn ends, and returns the turn's events: `list[dict]`, one per JSON line on the CLI's stdout. Lines that aren't JSON objects are skipped. If the CLI exits mid-turn, returns what arrived. |
| `close()`           | Ends the CLI's input, waits for it to exit, and returns a [`RunResult`](#runresult). Safe to call twice. |
| `result`            | The `RunResult` once closed, else `None`.                                  |

`Session` is a context manager; leaving the block calls `close()`. The `RunResult`'s `stdout` holds every line the CLI wrote, events included. There is no timeout: a turn that never ends blocks `message()`.

## `build()`

```python
box.build() -> str
```

Builds the agent's image, then your `dockerfile` on top, and returns the tag. `run()` calls this every time.

Concurrent builds of one tag, from any process, take turns.

## Agents

`ClaudeAgent`, `CodexAgent` and `PiAgent`: constructors, options and credentials are on each [harness page](../harnesses/).

See also: [Guides](../guide/), [How It Works](../explanation/).
