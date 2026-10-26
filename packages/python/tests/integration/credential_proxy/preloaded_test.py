"""preloaded as the stdin of a real `docker run -i` and `docker exec -i`."""

import asyncio
import hashlib
import os
import secrets
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest

from adocker import Container, Image
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
        container = await Image(IMAGE).run(
            "-c",
            script,
            name=name,
            stdin=stdin,
            stdout=out.extend,
            stderr=err.extend,
            entrypoint="sh",
        )
        code = await container.wait()
    finally:
        await Container(name).remove()
    assert code == 0, err.decode()
    return out.decode().strip()


@pytest.fixture
async def container() -> AsyncIterator[str]:
    name = f"botbox-test-{uuid4().hex[:12]}"
    process = await asyncio.create_subprocess_exec(
        "docker",
        "run",
        "--detach",
        "--name",
        name,
        "--entrypoint",
        "sleep",
        IMAGE,
        "60",
        stdout=asyncio.subprocess.DEVNULL,
    )
    assert await process.wait() == 0
    yield name
    await Container(name).remove()


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
        process = await asyncio.create_subprocess_exec(
            "docker",
            "exec",
            container,
            "sh",
            "-c",
            'sha256sum </tmp/s | cut -d" " -f1',
            stdout=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        assert stdout.decode().strip() == digest(secret)

    async def it_leaves_no_descriptor_behind() -> None:
        before = {fd.name for fd in Path("/proc/self/fd").iterdir()}
        read = preloaded(b"Bearer one")
        try:
            await docker_run_reading(read, "cat >/dev/null")
        finally:
            os.close(read)
        assert {fd.name for fd in Path("/proc/self/fd").iterdir()} == before
