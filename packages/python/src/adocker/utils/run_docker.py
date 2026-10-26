import asyncio
import os
from tempfile import TemporaryFile

from adocker.DockerException import DockerException
from adocker.utils.execute import Sink, Stream, execute

STDERR_LIMIT = 64 * 1024


async def run_docker(
    *args: str,
    stdin: Stream = asyncio.subprocess.DEVNULL,
    stdout: Sink | None = None,
    stderr: Sink | None = None,
) -> str:
    """Run `docker` with `args` to its exit and return its stdout, unless `stdout` is a sink.

    Raise DockerException if it fails, with the end of its stderr unless `stderr` is a sink.
    If this is cancelled or fails first, the client's group is stopped and reaped before the
    error propagates.
    """
    with TemporaryFile() as out, TemporaryFile() as err:
        code = await execute(args, stdin=stdin, stdout=stdout or out, stderr=stderr or err)
        if code != 0:
            err.seek(max(err.seek(0, os.SEEK_END) - STDERR_LIMIT, 0))
            raise DockerException(["docker", *args], code, err.read().decode(errors="replace"))
        out.seek(0)
        return out.read().decode(errors="replace")
