# botbox

Run a coding agent inside a locked-down Docker container.

[![CI](https://github.com/thekevinscott/botbox/actions/workflows/python.yml/badge.svg)](https://github.com/thekevinscott/botbox/actions/workflows/python.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

## Goals

An experiment that puts an agent in a box needs five things:

1. **A pre-configured agent CLI.** Claude Code or Pi pre-configured.
2. **No capabilities, no privilege escalation.** `--cap-drop ALL`, `no-new-privileges`, no setuid binaries.
3. **Network only to an allowlist.** No network access beyond the whitelist.
4. **Mounted directories.** Read-only or read-write
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
from botbox import Botbox, ClaudeAgent

agent = ClaudeAgent()
box = Botbox(agent)

result = box.run(
    command='claude -p "Make the failing tests pass please" --model claude-opus-5.5 --effort high',
    mounts=[
        ("./tests", "/tests", "ro"),
        ("./work", "/work", "rw"),
    ],
    workdir="/work", # optional; where the command starts. Must be a mounted path.
)

print(result.stdout)
print(result.proxy)
```


`run()` builds the image, creates a private network and a proxy sidecar, stages your credentials into a temporary home directory, runs the command, reads the transcript and proxy log out, deletes the temporary home, tears the network down, and returns.

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

### `run()`

```python
box.run(
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

`RunResult`: `stdout`, `stderr`, `exit_code`, `transcript`, `proxy`. Nothing parsed.

| Field        | What it is                                                                     |
| ------------ | ------------------------------------------------------------------------------ |
| `transcript` | `dict[str, str]`: path relative to the agent's home → file contents.            |
| `proxy`      | `str`: the proxy log.                                                           |

A non-zero exit is a normal `RunResult`. API errors inside the container are the CLI's to handle; they show up in `exit_code` and `stderr`. If the Docker daemon dies mid-run, `run()` still returns a `RunResult` with whatever transcript and proxy log exist. `run()` raises only when setup fails or the run is interrupted.

### `build()`

```python
box.build() -> str
```

Builds the agent's image, then your `dockerfile` on top, and returns the tag. `run()` calls this every time.

### Mounts

Plain bind mounts. Missing host paths raise.

```python
mounts=[
    ("./reference", "/reference", "ro"),
    ("./out",       "/out",       "rw"),
]
```

if workdir provided, `workdir` must be a mounted path or inside one; otherwise `run()` raises. Docker would create it root-owned and the agent could not write to it.

### Home and credentials

Each run gets a fresh temporary home, mounted at the agent's home path. Credentials (Claude Code: `~/.claude/.credentials.json`) are copied in before the command starts. After it exits, transcript files are read into `result.transcript` and the temporary home is deleted.

### Network

The container joins a Docker `--internal` network. The only way out is a CONNECT proxy that denies by default. The agent contributes its own hosts (`api.anthropic.com` for Claude Code); add more with `allow`:

```python
Botbox(ClaudeAgent(), allow=["registry.npmjs.org"])
```

Every connection, admitted or refused, is logged to `result.proxy`. Network and proxy are per run and removed afterwards, including on failure.

### Commands

`command` is a shell string, passed through unchanged. No `ENTRYPOINT`.

```python
command='claude -p "Fix the tests" --output-format json'
command=f'claude --resume {session_id} -p "Continue"'
```

## Extending the image

Agent images contain the CLI, its runtime, `git`, and `ca-certificates`. Everything else goes in your own Dockerfile, `FROM` the agent's image:

```dockerfile
FROM botbox-claude:latest

USER root
RUN npm install -g vitest@2.1.3
USER node
```

```python
box = Botbox(ClaudeAgent(), dockerfile="./Dockerfile")
```

The build context is the Dockerfile's directory. There is no network at run time, so installs happen here.

Two rules: end as `USER node`; leave the agent's home where it is.

## Agents

An agent is a Dockerfile plus a class that knows the home path, the credentials file, the transcript files, and the hosts the CLI needs.

| Agent       | Class         | Dockerfile          | Status     |
| ----------- | ------------- | ------------------- | ---------- |
| Claude Code | `ClaudeAgent` | `claude.Dockerfile` | supported  |
| pi          | `PiAgent`     | `pi.Dockerfile`     | image only |

No shared base image. To add an agent: one Dockerfile, one class, one row.

## Sample consumer Dockerfile extension

The layer `porting-harness` uses. The reference is mounted at run time, not copied in.

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

USER node
```

```python
box = Botbox(ClaudeAgent(), dockerfile=Path(__file__).parent / "Dockerfile")

result = box.run(
    command=f'claude -p {shlex.quote(prompt)} --model {model} --effort {effort}',
    mounts=[(reference, "/input", "ro"), (output_directory, "/target", "rw")],
    workdir="/target",
)
```

## Development

```sh
cd packages/python
uv sync
uv run pytest                  # unit, no Docker
uv run pytest -m integration   # real daemon
uv run pytest -m e2e           # builds images, runs a real prompt
```


## License

MIT. See [LICENSE](./LICENSE).

## Internal - Checks

- [ ] Check the build context. A fully cached `docker build` should take ~0.3s.
- [ ] Transcripts and the proxy log are synced to a host temp directory during the run, so a daemon crash loses nothing. `run()` reads them from there into `RunResult`. The directory is never exposed.
- [ ] add test for docker daemon dying
