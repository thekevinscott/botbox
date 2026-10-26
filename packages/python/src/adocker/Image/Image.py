import asyncio
import json
from collections.abc import Mapping, Sequence
from typing import Any

from adocker.Container import Container
from adocker.DockerException import DockerException
from adocker.Image.create_args import create_args
from adocker.Image.started import started
from adocker.Image.StdinPipe import StdinPipe
from adocker.Mount import Mount
from adocker.utils import Sink, Stream, execute, run_docker, settle

PIPE = asyncio.subprocess.PIPE
DEVNULL = asyncio.subprocess.DEVNULL


class Image:
    """An image, by `tag`: built, pulled or already on the daemon."""

    def __init__(self, tag: str) -> None:
        self.tag = tag

    async def inspect(self) -> dict[str, Any]:
        """Its id, tags and config. Raises DockerException if there is no such image."""
        [details] = json.loads(await run_docker("image", "inspect", "--format", "json", self.tag))
        result: dict[str, Any] = details
        return result

    async def run(  # noqa: PLR0913
        self,
        *command: str,
        name: str,
        stdin: Stream = DEVNULL,
        stdout: Sink | None = None,
        stderr: Sink | None = None,
        init: bool = False,
        rm: bool = False,
        labels: Mapping[str, str] | None = None,
        user: str | None = None,
        env: Mapping[str, str] | None = None,
        mounts: Sequence[Mount] = (),
        tmpfs: Sequence[str] = (),
        workdir: str | None = None,
        network: str | None = None,
        pid: str | None = None,
        pids_limit: int | None = None,
        cap_drop: Sequence[str] = (),
        security_opt: Sequence[str] = (),
        log_driver: str | None = None,
        entrypoint: str | None = None,
    ) -> Container:
        """Create a container `name` that runs `command`, start it with an attached client, and
        return it once it is running.

        `stdin` is the client's stdin, passed with `--interactive` unless DEVNULL or None.
        PIPE gives the container a `stdin` writer that only this process holds. `stdout` and
        `stderr` are sinks, handed each chunk of output as it arrives; without one, the
        output is dropped. The other options are `docker run`'s flags of the same names.

        Raises DockerException if the container can't be created, with docker's error handed
        to `stderr` too. A client that exits before the container starts is returned anyway,
        for `wait` to report.
        """
        interactive = stdin not in (None, DEVNULL)
        create = create_args(
            self.tag,
            command,
            name=name,
            interactive=interactive,
            init=init,
            rm=rm,
            labels=labels or {},
            user=user,
            env=env or {},
            mounts=mounts,
            tmpfs=tmpfs,
            workdir=workdir,
            network=network,
            pid=pid,
            pids_limit=pids_limit,
            cap_drop=cap_drop,
            security_opt=security_opt,
            log_driver=log_driver,
            entrypoint=entrypoint,
        )
        try:
            await run_docker(*create)
        except DockerException as error:
            if stderr is not None:
                stderr(error.stderr.encode())
            raise
        created: str = (await Container(name).inspect())["Created"]
        args = ["start", "--attach", *(["--interactive"] if interactive else []), name]
        pipe = await StdinPipe.open() if stdin == PIPE else None
        spawned: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        client = asyncio.ensure_future(
            attach(args, stdin if pipe is None else pipe, stdout, stderr, spawned)
        )
        running = asyncio.ensure_future(started(Container(name), created))
        try:
            try:
                await asyncio.wait({running, client}, return_when=asyncio.FIRST_COMPLETED)
                if running.done():
                    running.result()
                elif not spawned.done():
                    await client
            finally:
                running.cancel()
                await settle(asyncio.gather(running, return_exceptions=True))
        except BaseException:
            client.cancel()
            try:
                await settle(asyncio.gather(client, return_exceptions=True))
            finally:
                if pipe is not None:
                    pipe.writer.close()
            raise
        return Container(
            name,
            client=client,
            stdin=None if pipe is None else pipe.writer,
            docker_command=["docker", *args],
        )


async def attach(
    args: list[str],
    stdin: Stream | StdinPipe,
    stdout: Sink | None,
    stderr: Sink | None,
    started: asyncio.Future[None],
) -> int:
    """Run the client to its exit, then let go of a stdin pipe's read end."""
    try:
        return await execute(
            args,
            stdin=stdin.read if isinstance(stdin, StdinPipe) else stdin,
            stdout=DEVNULL if stdout is None else stdout,
            stderr=DEVNULL if stderr is None else stderr,
            started=started,
        )
    finally:
        if isinstance(stdin, StdinPipe):
            stdin.release()
