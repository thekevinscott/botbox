import asyncio
import os
from tempfile import TemporaryFile

from adocker.DockerException import DockerException
from adocker.utils.execute import Stream, execute

STDERR_LIMIT = 64 * 1024


async def run_docker(*args: str, stdin: Stream = asyncio.subprocess.DEVNULL) -> str:
    """Run `docker` with `args` to its exit and return its stdout.

    Raise DockerException with the end of its stderr if it fails. If this is cancelled or
    fails first, the client's group is stopped and reaped before the error propagates.
    """
    with TemporaryFile() as out, TemporaryFile() as err:
        code = await execute(args, stdin=stdin, stdout=out, stderr=err)
        if code != 0:
            err.seek(max(err.seek(0, os.SEEK_END) - STDERR_LIMIT, 0))
            raise DockerException(["docker", *args], code, err.read().decode(errors="replace"))
        out.seek(0)
        return out.read().decode(errors="replace")
