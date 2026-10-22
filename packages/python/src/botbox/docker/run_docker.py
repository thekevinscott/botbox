import asyncio

from botbox.docker.DockerException import DockerException
from botbox.docker.reap import reap
from botbox.docker.settle import settle
from botbox.docker.spawn import spawn
from botbox.docker.tail import tail

STDERR_LIMIT = 64 * 1024


async def run_docker(*args: str) -> str:
    """Run `docker` with `args` to its exit and return its stdout.

    Raise DockerException with the end of its stderr if it fails. If this is cancelled or
    fails first, the client is stopped and reaped before the error propagates.
    """
    process = await spawn(
        args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    stdout = asyncio.ensure_future(process.stdout.read())
    stderr = asyncio.ensure_future(tail(process.stderr, STDERR_LIMIT))
    try:
        code = await process.wait()
        out, err = await stdout, await stderr
    except BaseException:
        await settle(reap(process, stdout, stderr))
        raise
    if code != 0:
        raise DockerException(["docker", *args], code, err.decode(errors="replace"))
    return out.decode(errors="replace")
