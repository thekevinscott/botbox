import asyncio
import json
from collections.abc import Sequence
from typing import Any

from adocker.utils import Sink, Stream, run_docker


class Container:
    """A container, by `name`.

    `Image.run` returns one holding its attached client, `stdin` if it asked for a pipe, and
    the `docker_command` that started it. Wrap a name to reach a container started elsewhere.
    """

    def __init__(
        self,
        name: str,
        *,
        client: "asyncio.Task[int] | None" = None,
        stdin: asyncio.StreamWriter | None = None,
        docker_command: Sequence[str] = (),
    ) -> None:
        self.name = name
        self.client = client
        self.stdin = stdin
        self.docker_command = list(docker_command)

    async def wait(self) -> int:
        """Wait for it to stop and return its exit code.

        With an attached client, that is the client's code, once its output is in. Cancelling
        the wait kills the client and reaps its group; the container lives on.
        """
        if self.client is not None:
            return await self.client
        return int(await run_docker("wait", self.name))

    async def stop(self, seconds: int) -> None:
        """Stop it, killing it if it is still up after `seconds`."""
        await run_docker("stop", "--time", str(seconds), self.name)

    async def remove(self) -> None:
        """Remove it, running or not."""
        await run_docker("rm", "--force", self.name)

    async def inspect(self) -> dict[str, Any]:
        """Its state and config. Raises DockerException if there is no such container."""
        [details] = json.loads(
            await run_docker("container", "inspect", "--format", "json", self.name)
        )
        result: dict[str, Any] = details
        return result

    async def exec(
        self,
        *command: str,
        stdin: Stream = asyncio.subprocess.DEVNULL,
        stdout: Sink | None = None,
        stderr: Sink | None = None,
    ) -> None:
        """Run `command` in it on `stdin`, handing its output to the `stdout` and `stderr` sinks.

        Without a sink, stdout is dropped. Raises DockerException if it exits non-zero, with
        the end of its stderr unless that went to a sink.
        """
        interactive = ["--interactive"] if stdin not in (None, asyncio.subprocess.DEVNULL) else []
        await run_docker(
            "exec",
            *interactive,
            self.name,
            *command,
            stdin=stdin,
            stdout=stdout or (lambda _: None),
            stderr=stderr,
        )
