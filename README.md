# botbox

Run a coding agent inside a locked-down Docker container.

[![CI](https://github.com/thekevinscott/botbox/actions/workflows/python.yml/badge.svg)](https://github.com/thekevinscott/botbox/actions/workflows/python.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

Docs: https://thekevinscott.github.io/botbox/

## Goals

An experiment that puts an agent in a box needs five things:

1. **A pre-configured agent CLI.** Claude Code or Pi pre-configured.
2. **No capabilities, no privilege escalation.** `--cap-drop ALL`, `no-new-privileges`, no setuid binaries.
3. **Network only to an allowlist.** No network access beyond the whitelist.
4. **Mounted directories.** Read-only or read-write.
5. **Logs available.** The agent's transcript and the proxy's log come back on the result.

The Python SDK is the public API.

## Installation

```bash
pip install botbox
```

(planned, not yet built):
```bash
npm install @thekevinscott/botbox
```

Requires Docker.

## Quick start

`botbox` exposes a Python and (planned, not yet built) Node SDK.

```python
import asyncio

from botbox import Botbox, ClaudeAgent


async def main() -> None:
    agent = ClaudeAgent(model="claude-opus-5", effort="high")
    async with Botbox(agent) as box:
        result = await box.run(
            command=agent.command("Make the failing tests pass please"),
            mounts=[
                ("./tests", "/tests", "ro"),
                ("./work", "/work", "rw"),
            ],
            workdir="/work", # optional; where the command starts. Must be a mounted path.
        )
    print(result.stdout)
    print(result.proxy.read_text())


asyncio.run(main())
```


`run()` builds the image, starts a proxy sidecar, stages your credentials into a temporary home directory, runs the command, moves the transcript and copies the proxy log into the result's own temp directory, deletes the temporary home, stops the proxy, and returns.

The API is asyncio. A sync caller wraps each call in `asyncio.run(...)`.

## Usage

### `Botbox`

```python
Botbox(agent: Agent, *, dockerfile: str | Path | None = None, allow: Sequence[str] = ())
```

| Argument     | What it is                                                     |
| ------------ | -------------------------------------------------------------- |
| `agent`      | Which agent. See [Agents](#agents).                            |
| `dockerfile` | Your layer on top of the agent's image. See [Extending the image](#extending-the-image). |
| `allow`      | Hostnames the proxy admits, in addition to the agent's own.    |

`Botbox` is an async context manager. Inside `async with Botbox(...) as box:`, SIGTERM cancels the task that entered the block, so a run in progress tears down, then the block raises `SystemExit(143)`. `build()`, `run()` and `session()` work without the block too.

### `run()`

```python
await box.run(
    command: str,
    *,
    mounts: Sequence[tuple[str | Path, str | Path, Literal["ro", "rw"]]] = (),
    workdir: str | Path | None = None,
) -> RunResult
```

| Argument         | What it is                                                              |
| ---------------- | ----------------------------------------------------------------------- |
| `command`        | Shell command line, run as `sh -c`.                                     |
| `mounts`         | Bind mounts: host path, container path, mode. See [Mounts](#mounts).    |
| `workdir`        | Where the command starts. Must be a mounted path. Defaults to the agent's home. |

`RunResult`: `stdout`, `stderr`, `exit_code`, `image`, `files`. Nothing parsed.

| Field        | What it is                                                                     |
| ------------ | ------------------------------------------------------------------------------ |
| `image`      | `str`: the tag that ran: your layer's when `dockerfile` is given, else the agent's. |
| `files`      | `Path`: a temp directory the result owns, deleted when the result is garbage collected. |
| `transcript` | `Path`: `files / "transcript"`, each file at its path relative to the agent's home. |
| `proxy`      | `Path`: `files / "proxy.log"`, the proxy log.                                   |

`result.save(dest)` copies `files` somewhere permanent. `result.cleanup()`, or `with result:`, deletes it sooner.

The container is removed once its exit code is read. Everything in the result is captured before it goes. Anything the command wrote outside the mounts and the agent's home goes with it, so write what you want to keep to a mount.

A non-zero exit is a normal `RunResult`. API errors inside the container are the CLI's to handle; they show up in `exit_code` and `stderr`. If the Docker daemon dies mid-run, `run()` still returns a `RunResult` with whatever transcript and proxy log exist, and `exit_code` -1. `run()` raises only when setup fails or the run is cancelled. Docker failures in setup raise `botbox.DockerException`, and so does a container that never started: an image the daemon can't find raises with `return_code` 125. Cancelling the task, or an `asyncio.timeout` firing, removes the run's containers and temp home before the cancel propagates.

### `build()`

```python
await box.build() -> str
```

Builds the agent's image, then your `dockerfile` on top, and returns the tag. `run()` calls this every time.

Concurrent builds of one tag, from any process, take turns.

### Mounts

Plain bind mounts. Missing host paths raise.

```python
mounts=[
    ("./reference", "/reference", "ro"),
    ("./out",       "/out",       "rw"),
]
```

If given, `workdir` must be a mounted path or inside one; otherwise `run()` raises. Docker would create it root-owned and the agent could not write to it.

### Home and credentials

Each run gets a fresh temporary home, mounted at the agent's home path. After the command exits, transcript files are moved into `result.transcript` and the temporary home is deleted.

`ClaudeAgent` authenticates one of two ways, never both:

- Default: `~/.claude/.credentials.json` is copied into the temporary home.
- `ClaudeAgent(api_key=key)`: the key is written to `.claude/api_key` (mode 600) in the temporary home, with a `settings.json` whose `apiKeyHelper` reads it.

`PiAgent` likewise, never both:

- Default: `~/.pi/agent/auth.json` is copied into the temporary home, and `models.json` beside it if it exists.
- `PiAgent(provider, api_key=key)`: a fresh `.pi/agent/auth.json` (mode 600) holds the key for `provider` and nothing else. No host files are read.

botbox reads no `.env` and no environment variables. The caller passes the key.

### Network

The container runs with `--network none`. The only way out is a unix socket to a CONNECT proxy that denies by default. The agent contributes its own hosts (`api.anthropic.com` for Claude Code); add more with `allow`:

```python
Botbox(ClaudeAgent(), allow=["registry.npmjs.org"])
```

Every connection, admitted or refused, is logged to `result.proxy`. The proxy is per run and removed afterwards, including on failure. Tested on Linux only.

### Commands

`command` is a shell string, passed through unchanged. No `ENTRYPOINT`.

```python
command='claude -p "Fix the tests" --output-format json'
command=f'claude --resume {session_id} -p "Continue"'
```

## Extending the image

Agent images contain the CLI, its runtime, `git`, and `ca-certificates`. The pi image adds `python3`, `ripgrep`, and `fd`. Everything else goes in your own Dockerfile, `FROM` the agent's image:

```dockerfile
FROM botbox-claude:latest

USER root
RUN npm install -g vitest@2.1.3
USER user
```

```python
box = Botbox(ClaudeAgent(), dockerfile="./Dockerfile")
```

The build context is the Dockerfile's directory. There is no network at run time, so installs happen here.

Two rules: end as `USER user`; leave the agent's home where it is.

## Agents

An agent is a Dockerfile plus a class that knows the home path, the credentials file, the transcript files, the hosts the CLI needs, and how to invoke the CLI.

| Agent       | Class         | Dockerfile                 | Status     |
| ----------- | ------------- | -------------------------- | ---------- |
| Claude Code | `ClaudeAgent` | `agents/claude/Dockerfile` | supported  |
| pi          | `PiAgent`     | `agents/pi/Dockerfile`     | image only |

No shared base image. To add an agent: one Dockerfile, one class, one row.

### `command()`

```python
ClaudeAgent(model: str | None = None, effort: str | None = None, *, api_key: str | None = None)
PiAgent(provider: str, model: str | None = None, *, api_key: str | None = None)

agent.command(prompt: str) -> str
```

Renders the agent's CLI invocation for a prompt: `claude -p <prompt> --output-format json --dangerously-skip-permissions --strict-mcp-config`, plus `--model` and `--effort` when set. The prompt is shell-quoted. `run()` still takes any string; `command()` is the agent's.

`PiAgent` requires `provider` first because it selects the egress allowlist.

```python
agent = ClaudeAgent(model="claude-opus-5", effort="high")
await box.run(agent.command("Fix the tests"))
```

## Sample consumer Dockerfile extension

The layer `port_codebase` uses. The reference is mounted at run time, not copied in.

```dockerfile
FROM botbox-claude:latest

USER root

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /usr/local/bin/
ENV UV_PYTHON_INSTALL_DIR=/usr/local/share/uv/python \
    UV_PYTHON_BIN_DIR=/usr/local/bin \
    UV_TOOL_DIR=/usr/local/share/uv/tools \
    UV_TOOL_BIN_DIR=/usr/local/bin
RUN uv python install --preview-features python-install-default --default 3.14.3
RUN uv tool install --python 3.14.3 pytest==9.1.1 --with pytest-describe==3.2.0

RUN npm install -g vitest@2.1.3
ENV NODE_PATH=/usr/local/lib/node_modules

USER user
```

```python
agent = ClaudeAgent(model=model, effort=effort)
box = Botbox(agent, dockerfile=Path(__file__).parent / "Dockerfile")

result = await box.run(
    command=agent.command(prompt),
    mounts=[(source, "/input", "ro"), (output, "/target", "rw")],
    workdir="/target",
)
```

## License

MIT. See [LICENSE](./LICENSE).

## Internal - Checks

- [ ] Check the build context. A fully cached `docker build` should take ~0.3s.
- [x] Transcripts and the proxy log are synced to a host temp directory during the run, so a daemon crash loses nothing. `run()` reads them from there into `RunResult`. The directory is never exposed.
- [x] add test for docker daemon dying
- [x] add test for concurrent builds of one tag
