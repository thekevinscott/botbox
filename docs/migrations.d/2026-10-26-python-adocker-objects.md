# adocker: classes replace the free functions

## Summary

`adocker` exports `Container`, `DockerException`, `Dockerfile`, `Image` and `Volume`. The free functions (`build`, `run`, `remove`, `stop`, `version`, `volume`, `inspect_container`, `inspect_image`) are gone. In botbox, `Session` loses its `stdout` and `stderr` fields, and a run's streams go through its temp directory.

## Required changes

```python
# before
from adocker import build, remove, run, version, volume
await build(context, tag="x:latest", file=context / "Dockerfile")
code = await run(["--name", "box", "x:latest", "true"], stdout=out, stderr=err)
await remove("box")
info = await version()
async with volume("v", label="k=v"): ...

# after
from adocker import Container, Dockerfile, Image, Volume
image = await Dockerfile(context / "Dockerfile", context=context).build("x:latest")
container = await Image("x:latest").run("true", name="box", stdout=out.extend, stderr=err.extend)
code = await container.wait()
await Container("box").remove()
async with Volume("v", labels={"k": "v"}): ...
```

- `Image.run` takes the flags as keywords (`env` and `labels` as mappings, `mounts` as `(source, target, mode)` tuples) and requires `name`. `--interactive` follows from `stdin`.
- `stdout` and `stderr` are callables handed each chunk, not bytearrays or files.
- `Container.wait()` returns the attached client's code when the container came from `Image.run`, and `docker wait`'s otherwise.
- botbox's `Session(...)` takes `(agent, stdin, client, readline)`. Read a session's streams from `output`.

## Deprecations removed

None. The functions are removed without a deprecation period.

## Behavior changes without code changes

- A run's or session's `stdout.txt`, `stderr.txt` and `proxy.log` are written to its temp directory, under `TMPDIR`, and copied to `output`. Keep `TMPDIR` on disk; a tmpfs puts the streams in memory.
- A write to `output` that fails is a `RuntimeWarning`, and the run carries on without that file.
- A daemon that goes away mid-run raises `DockerException` with the client's code and stderr. It used to return `RunResult(exit_code=-1)`. `version()` is gone with no replacement: shell out to `docker version` if you need it.
- `DockerException.stderr` from the agent holds the last 64 KiB of its stderr, not `See <path>`.
- A proxy whose `docker` client fails to launch raises that error directly, not a `RuntimeError` naming the proxy.

## Verification

```python
import asyncio

from adocker import Image

print(asyncio.run(Image("busybox:latest").inspect())["Id"])
```

Expected (unverified): the image's `sha256:` id, after `docker pull busybox:latest`.
