import asyncio

from adocker.Capture import Capture
from adocker.DockerException import DockerException
from adocker.execute import execute

STDERR_LIMIT = 64 * 1024


async def run_docker(*args: str) -> str:
    """Run `docker` with `args` to its exit and return its stdout.

    Raise DockerException with the end of its stderr if it fails. If this is cancelled or
    fails first, the client's group is stopped and reaped before the error propagates.
    """
    out, err = bytearray(), bytearray()
    async with Capture(out) as stdout, Capture(err, STDERR_LIMIT) as stderr:
        code = await execute(args, stdin=asyncio.subprocess.DEVNULL, stdout=stdout, stderr=stderr)
    if code != 0:
        raise DockerException(["docker", *args], code, err.decode(errors="replace"))
    return out.decode(errors="replace")
