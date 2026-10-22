import asyncio

from botbox.docker.collect import collect
from botbox.docker.DockerException import DockerException
from botbox.docker.ended import ended
from botbox.docker.exit_code import exit_code
from botbox.docker.finish import finish
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
    process = await spawn(
        args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    out, err = bytearray(), bytearray()
    readers = (
        asyncio.ensure_future(collect(process.stdout, out)),
        asyncio.ensure_future(collect(process.stderr, err, STDERR_LIMIT)),
    )
    try:
        code = await exit_code(process)
        async with asyncio.timeout(LINGER):
            await ended(process, readers)
    except TimeoutError:
        await settle(reap(process, *readers))
    except BaseException:
        await settle(reap(process, *readers))
        raise
    finally:
        await finish(process, readers)
    if code != 0:
        raise DockerException(["docker", *args], code, err.decode(errors="replace"))
    return out.decode(errors="replace")
