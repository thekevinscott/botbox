import asyncio
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

from python_on_whales.exceptions import DockerException

STDERR_LIMIT = 64 * 1024


async def buildx(
    context: Path, *, tag: str, file: Path, contexts: Mapping[str, str | Path]
) -> None:
    """Build and load `tag` with `docker buildx build`; raise `DockerException` if it fails.

    The error carries the last `STDERR_LIMIT` bytes of stderr. Cancelling stops the client and
    waits for it to exit, however many cancels arrive meanwhile; BuildKit drops the build when
    its client goes.
    """
    argv = [
        "docker",
        "buildx",
        "build",
        "--load",
        "--progress=quiet",
        "--tag",
        tag,
        "--file",
        str(file),
        *[
            flag
            for name, path in contexts.items()
            for flag in ("--build-context", f"{name}={path}")
        ],
        str(context),
    ]
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
        # Out of the caller's process group: Ctrl-C reaches it only as a cancel.
        start_new_session=True,
    )
    assert process.stderr is not None
    tail = b""
    try:
        while chunk := await process.stderr.read(STDERR_LIMIT):
            tail = (tail + chunk)[-STDERR_LIMIT:]
        code = await process.wait()
    except BaseException:
        with suppress(ProcessLookupError):
            process.terminate()
        reaped = asyncio.ensure_future(process.wait())
        while not reaped.done():
            with suppress(asyncio.CancelledError):
                await asyncio.shield(reaped)
        raise
    if code != 0:
        raise DockerException(argv, code, stderr=tail.decode(errors="replace").encode())
