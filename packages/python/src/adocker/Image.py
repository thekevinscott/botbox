import asyncio
import json
from collections.abc import Mapping, Sequence
from typing import Any

from adocker.Container import Container
from adocker.execute import Sink, Stream, execute
from adocker.run_args import Mount, run_args
from adocker.run_docker import run_docker
from adocker.settle import settle
from adocker.StdinPipe import StdinPipe

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
        """Start `command` in a container `name` with an attached `docker run`, and return it
        once the client has started.

        `stdin` is the client's stdin, passed with `--interactive` unless DEVNULL or None.
        PIPE gives the container a `stdin` writer that only this process holds. `stdout` and
        `stderr` are sinks, handed each chunk of output as it arrives; without one, the
        output is dropped. The other options are `docker run`'s flags of the same names.
        """
        pipe = await StdinPipe.open() if stdin == PIPE else None
        args = run_args(
            self.tag,
            command,
            name=name,
            interactive=stdin not in (None, DEVNULL),
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
        started: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        client = asyncio.ensure_future(
            attach(args, stdin if pipe is None else pipe, stdout, stderr, started)
        )
        try:
            waiting: set[asyncio.Future[Any]] = {started, client}
            await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
            if not started.done():
                await client
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
