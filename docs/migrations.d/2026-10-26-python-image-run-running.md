# adocker: Image.run returns once the container is running

## Summary

`Image.run` creates the container with `docker create`, starts it with an attached
`docker start --attach`, and returns once the daemon reports it started. It used to return as
soon as an attached `docker run` client was spawned.

## Required changes

Code that checks for a container that never started by its exit code changes:

```python
# before
try:
    await box.run(command)
except DockerException as error:
    missing_image = error.return_code == 125

# after: `docker create` failed, which exits 1
try:
    await box.run(command)
except DockerException as error:
    missing_image = error.docker_command[:2] == ["docker", "create"]
```

## Deprecations removed

None.

## Behavior changes without code changes

- `Image.run` raises `DockerException` when the container can't be created, instead of
  returning a container whose `wait` gives 125. Docker's error is also handed to the
  `stderr` sink. botbox's `session()` raises on entering.
- `Container.docker_command`, and the `docker_command` of a `DockerException` botbox raises
  for the agent's client, is `docker start --attach [--interactive] <name>`.
- Image pull progress for a missing image is no longer passed to the `stderr` sink.
- Waits put on top of `Image.run` for the container to come up, such as watching its output
  for a ready line before an `exec`, are no longer needed for that purpose.

## Verification

```python
import asyncio

from adocker import Image

async def main():
    container = await Image("busybox").run("sleep", "60", name="check-running")
    await container.exec("true")
    print((await container.inspect())["State"]["Running"])
    await container.remove()
    await container.wait()

asyncio.run(main())
```

Expected (unverified): `True`, and the script exits.
