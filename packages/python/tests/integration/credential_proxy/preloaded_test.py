"""preloaded as the stdin of a real `docker run -i` and `docker exec -i`."""

import asyncio
import hashlib
import os
import secrets
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest

from adocker.remove import remove
from adocker.run import run
from adocker.run_docker import run_docker
from botbox.credential_proxy.envoy_config import IMAGE
from botbox.credential_proxy.preloaded import preloaded

# Past the small writes, short of a 64 KiB pipe buffer.
LARGE = 60 * 1024
SHA = 'sha256sum | cut -d" " -f1'


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def docker_run_reading(stdin: int, script: str) -> str:
    out, err = bytearray(), bytearray()
    name = f"botbox-test-{uuid4().hex[:12]}"
    try:
        args = ["--interactive", "--name", name, "--entrypoint", "sh", IMAGE, "-c", script]
        code = await run(args, stdin=stdin, stdout=out, stderr=err)
    finally:
        await remove(name)
    assert code == 0, err.decode()
    return out.decode().strip()


@pytest.fixture
async def container() -> AsyncIterator[str]:
    name = f"botbox-test-{uuid4().hex[:12]}"
    await run_docker("run", "--detach", "--name", name, "--entrypoint", "sleep", IMAGE, "60")
    yield name
    await remove(name)


async def docker_exec_reading(container: str, stdin: int, script: str) -> int:
    process = await asyncio.create_subprocess_exec(
        "docker", "exec", "--interactive", container, "sh", "-c", script, stdin=stdin
    )
    return await process.wait()


def describe_preloaded() -> None:
    @pytest.mark.parametrize("size", [32, LARGE])
    async def it_reaches_docker_run_intact(size: int) -> None:
        secret = secrets.token_bytes(size)
        read = preloaded(secret)
        try:
            assert await docker_run_reading(read, SHA) == digest(secret)
        finally:
            os.close(read)

    @pytest.mark.parametrize("size", [32, LARGE])
    async def it_reaches_docker_exec_intact(container: str, size: int) -> None:
        secret = secrets.token_bytes(size)
        read = preloaded(secret)
        try:
            assert await docker_exec_reading(container, read, "cat >/tmp/s") == 0
        finally:
            os.close(read)
        assert (
            await run_docker("exec", container, "sh", "-c", 'sha256sum </tmp/s | cut -d" " -f1')
        ).strip() == (digest(secret))

    async def it_leaves_no_descriptor_behind() -> None:
        before = {fd.name for fd in Path("/proc/self/fd").iterdir()}
        read = preloaded(b"Bearer one")
        try:
            await docker_run_reading(read, "cat >/dev/null")
        finally:
            os.close(read)
        assert {fd.name for fd in Path("/proc/self/fd").iterdir()} == before
