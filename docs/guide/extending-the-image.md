# Extending the image

There is no network at run time, so anything the agent needs beyond the CLI, its runtime, `git`, and `ca-certificates` is installed in your own Dockerfile.

## Write a Dockerfile `FROM` the agent's image

```dockerfile
FROM botbox-claude:latest

USER root
RUN npm install -g vitest@2.1.3
USER user
```

Two rules: end as `USER user`; leave the agent's home where it is.

## Pass it to `Botbox`

```python
box = Botbox(ClaudeAgent(), dockerfile="./Dockerfile")
```

The build context is the Dockerfile's directory. `run()` builds the agent's image, then your Dockerfile on top, every time.

## Example: Python and Node test runners

The layer `port_codebase` uses. The source is mounted at run time, not copied in.

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

result = box.run(
    command=agent.command(prompt),
    mounts=[(source, "/input", "ro"), (output, "/target", "rw")],
    workdir="/target",
)
```

Next: [Mounting directories](./mounting-directories).
