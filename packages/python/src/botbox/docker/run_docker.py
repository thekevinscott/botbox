import asyncio

from botbox.docker.Capture import Capture
from botbox.docker.DockerException import DockerException
from botbox.docker.ended import ended
from botbox.docker.exit_code import exit_code
from botbox.docker.reap import reap
from botbox.docker.settle import settle
from botbox.docker.spawn import spawn

STDERR_LIMIT = 64 * 1024
# How long the client's descendants may keep its pipes open after it exits.
LINGER = 2


async def run_docker(*args: str) -> str:
    """Run `docker` with `args` to its exit and return its stdout.

    Raise DockerException with the end of its stderr if it fails. If this is cancelled or
    fails first, the client's group is stopped and reaped before the error propagates.
    """
    out, err = bytearray(), bytearray()
    async with Capture(out) as stdout, Capture(err, STDERR_LIMIT) as stderr:
        try:
            process = await spawn(
                args, stdin=asyncio.subprocess.DEVNULL, stdout=stdout.write, stderr=stderr.write
            )
        finally:
            stdout.release()
            stderr.release()
        eofs = (stdout.eof, stderr.eof)
        try:
            code = await exit_code(process)
            async with asyncio.timeout(LINGER):
                await ended(process, eofs)
        except TimeoutError:
            await settle(reap(process, *eofs))
        except BaseException:
            await settle(reap(process, *eofs))
            raise
    if code != 0:
        raise DockerException(["docker", *args], code, err.decode(errors="replace"))
    return out.decode(errors="replace")
