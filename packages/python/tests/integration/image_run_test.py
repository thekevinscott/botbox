"""`Image.run` against the real daemon: the container it returns is already running."""

import asyncio
import subprocess
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from adocker import Container, Dockerfile, Image
from botbox.lockdown import PROXY_DIR, PROXY_IMAGE

TRIES = 5


@pytest.fixture
async def image() -> Image:
    """The proxy's image, which has sh."""
    return await Dockerfile(PROXY_DIR / "Dockerfile").build(PROXY_IMAGE)


@pytest.fixture
async def names() -> AsyncIterator[list[str]]:
    made: list[str] = []
    yield made
    for name in made:
        subprocess.run(["docker", "rm", "--force", name], capture_output=True, check=False)


async def run(image: Image, names: list[str]) -> Container:
    name = f"botbox-test-{uuid4().hex[:12]}"
    names.append(name)
    return await image.run("-c", "exec sleep 60", name=name, entrypoint="sh")


def describe_Image_run() -> None:
    async def it_returns_a_container_that_takes_an_exec_at_once(
        image: Image, names: list[str]
    ) -> None:
        for _ in range(TRIES):
            container = await run(image, names)
            await asyncio.wait_for(container.exec("true"), 10)
            assert (await container.inspect())["State"]["Running"] is True

    async def it_returns_a_container_that_a_remove_ends_at_once(
        image: Image, names: list[str]
    ) -> None:
        for _ in range(TRIES):
            container = await run(image, names)
            await container.remove()
            await asyncio.wait_for(container.wait(), 10)
