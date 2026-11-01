import asyncio
import os
from tempfile import TemporaryFile
from typing import IO, Any

from posix_tools import spawn

from adocker.DockerException import DockerException

type Stream = int | IO[Any] | None

STDERR_LIMIT = 64 * 1024


async def run_docker(
    *args: str,
    stdin: Stream = asyncio.subprocess.DEVNULL,
    stdout: Stream = None,
    stderr: Stream = None,
) -> str:
    """Run `docker` with `args` to its exit and return its stdout unless redirected.

    Raise DockerException if it fails, with the end of its stderr unless redirected.
    If this is cancelled or fails first, the client's group is stopped and reaped before the
    error propagates.
    """
    with TemporaryFile() as out, TemporaryFile() as err:
        async with spawn(
            "docker",
            *args,
            stdin=stdin,
            stdout=out if stdout is None else stdout,
            stderr=err if stderr is None else stderr,
        ) as process:
            code = await process.wait()
        if code != 0:
            err.seek(max(err.seek(0, os.SEEK_END) - STDERR_LIMIT, 0))
            raise DockerException(["docker", *args], code, err.read().decode(errors="replace"))
        out.seek(0)
        return out.read().decode(errors="replace")
