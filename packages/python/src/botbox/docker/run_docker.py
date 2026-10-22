import asyncio

from botbox.docker.DockerException import DockerException
from botbox.docker.ended import ended
from botbox.docker.exit_code import exit_code
from botbox.docker.harvest import harvest
from botbox.docker.spawn import spawn
from botbox.docker.stop import stop
from botbox.docker.tail import tail

STDERR_LIMIT = 64 * 1024
# How long the client's descendants may keep its pipes open after it exits.
LINGER = 2


async def run_docker(*args: str) -> str:
    """Run `docker` with `args` to its exit and return its stdout.

    Raise DockerException with the end of its stderr if it fails. If this is cancelled or
    fails first, the client's group is stopped and reaped before the error propagates.
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
        code = await exit_code(process)
        async with asyncio.timeout(LINGER):
            await ended(process, (stdout, stderr))
    except TimeoutError:
        await stop(process, stdout, stderr)
    except BaseException:
        await stop(process, stdout, stderr)
        raise
    if code != 0:
        raise DockerException(["docker", *args], code, harvest(stderr).decode(errors="replace"))
    return harvest(stdout).decode(errors="replace")
