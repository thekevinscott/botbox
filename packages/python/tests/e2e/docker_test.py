"""adocker against the real daemon. Every image and container is named `sdk-*`."""

import asyncio
import os
import subprocess
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

import pytest

from adocker import Container, Daemon, DockerException, Dockerfile, Image


def processes(needle: str) -> list[list[str]]:
    """The argv of every host process whose command line mentions `needle`."""
    found = []
    for cmdline in Path("/proc").glob("[0-9]*/cmdline"):
        with suppress(OSError):
            argv = cmdline.read_bytes().decode(errors="replace").split("\0")
            if any(needle in arg for arg in argv):
                found.append(argv)
    return found


def exists(kind: str, name: str) -> bool:
    return subprocess.run(["docker", kind, "inspect", name], capture_output=True).returncode == 0


async def until(condition: object, timeout: float = 60) -> None:
    async with asyncio.timeout(timeout):
        while not condition():  # type: ignore[operator]
            await asyncio.sleep(0.05)


@pytest.fixture
def name() -> Iterator[str]:
    name = f"sdk-{uuid4().hex[:12]}"
    yield name
    subprocess.run(["docker", "rm", "--force", name], capture_output=True)
    subprocess.run(["docker", "image", "rm", "--force", f"{name}:latest"], capture_output=True)


def dockerfile(directory: Path, *lines: str) -> Dockerfile:
    file = directory / "Dockerfile"
    file.write_text("FROM busybox:latest\n" + "".join(f"{line}\n" for line in lines))
    return Dockerfile(file)


def describe_docker() -> None:
    async def it_reports_the_server_version() -> None:
        assert (await Daemon().version())["Server"]["Version"]

    async def it_builds_an_image_with_a_named_context(name: str, tmp_path: Path) -> None:
        extra = tmp_path / "extra"
        extra.mkdir()
        (extra / "marker").write_text(name)
        file = dockerfile(tmp_path, "COPY --from=extra marker /marker")
        image = await file.build(f"{name}:latest", contexts={"extra": extra})
        assert image.tag == f"{name}:latest"
        assert exists("image", f"{name}:latest")

    async def it_raises_what_buildx_said_when_a_build_fails(name: str, tmp_path: Path) -> None:
        file = dockerfile(tmp_path, f"RUN echo {name}-broke >&2; exit 3")
        with pytest.raises(DockerException, match=f"{name}-broke"):
            await file.build(f"{name}:latest")

    async def it_runs_attached_then_waits_and_removes(name: str) -> None:
        read, write = os.pipe()
        os.write(write, b"through stdin")
        os.close(write)
        stdout = bytearray()
        try:
            container = await Image("busybox:latest").run(
                "sh", "-c", "cat; exit 7", name=name, stdin=read, stdout=stdout.extend
            )
            code = await container.wait()
        finally:
            os.close(read)
        assert code == 7
        assert stdout == b"through stdin"
        assert await Container(name).wait() == 7
        await container.remove()
        assert not exists("container", name)

    async def it_removes_a_container_that_does_not_exist(name: str) -> None:
        await Container(name).remove()

    async def it_stops_a_build_cancelled_twice(name: str, tmp_path: Path) -> None:
        step = f"sleep 83.5; echo {name}"
        file = dockerfile(tmp_path, f"RUN {step}")
        task = asyncio.create_task(file.build(f"{name}:latest"))
        await until(lambda: processes(step))
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        async with asyncio.timeout(10):
            with pytest.raises(asyncio.CancelledError):
                await task
        await until(lambda: not processes(f"{name}:latest"), timeout=5)
        await until(lambda: not processes(step), timeout=5)
