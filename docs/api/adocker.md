# `adocker`

```python
from adocker import DockerException, build, inspect_container, inspect_image, run
```

The async Docker client botbox runs on, for code that needs Docker outside a `Botbox`. It ships in the botbox wheel and drives the `docker` CLI. Every call is a coroutine; cancelling one stops the Docker client it started.

```python
await build(context: Path, *, tag: str, file: Path, contexts: Mapping[str, str | Path] | None = None) -> None
```

Builds `file` in `context` with `docker buildx build --load` and tags it `tag`. `contexts` adds named build contexts.

```python
await run(args: Sequence[str], *, stdin, stdout, stderr, limit: int | None = None) -> int
```

Runs an attached `docker run` with `args` and returns the client's exit code. `stdin`, `stdout` and `stderr` take a file, a descriptor or `None`. `stdout` and `stderr` can also be a `bytearray`, which collects the output, keeping the last `limit` bytes if given. A cancel stops the client but leaves the container, so pass `--rm` or remove it yourself.

```python
await inspect_image(image: str) -> dict[str, Any]
await inspect_container(container: str) -> dict[str, Any]
```

Return Docker's inspect record for one image or container. The image's id is `["Id"]`.

Any `docker` command that exits non-zero raises `DockerException`, with the command in `docker_command`, its `return_code` and its `stderr` as text. `run()` is the exception: it returns the exit code. `adocker.DockerException` is `botbox.DockerException`.

```python
out = bytearray()
await build(Path("."), tag="tool:latest", file=Path("Dockerfile"))
code = await run(["--rm", "tool:latest"], stdin=None, stdout=out, stderr=None)
image_id = (await inspect_image("tool:latest"))["Id"]
```
