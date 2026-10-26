"""wait_for_socket probing a real unix socket from inside the proxy's image."""

import asyncio
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from adocker import Container, Dockerfile
from botbox.credential_proxy.wait_for_socket import wait_for_socket
from botbox.lockdown import PROXY_DIR, PROXY_IMAGE

SOCKET = "/tmp/c.sock"
LISTEN = f"socat UNIX-LISTEN:{SOCKET},fork OPEN:/dev/null"


@pytest.fixture
def log(tmp_path: Path) -> Path:
    path = tmp_path / "log"
    path.write_text("envoy: starting\n")
    return path


@pytest.fixture
async def through() -> AsyncIterator[Container]:
    """A running container of the proxy's image, which has socat."""
    image = await Dockerfile(PROXY_DIR / "Dockerfile").build(PROXY_IMAGE)
    name = f"botbox-test-{uuid4().hex[:12]}"
    said = bytearray()
    container = await image.run(
        "-c", "echo up; exec sleep 60", name=name, entrypoint="sh", stdout=said.extend
    )
    while b"up" not in said:
        await asyncio.sleep(0.05)
    yield container
    subprocess.run(["docker", "rm", "--force", name], capture_output=True, check=False)


def client(container: Container) -> asyncio.Future[int]:
    return cast("asyncio.Future[int]", container.client)


def describe_wait_for_socket() -> None:
    async def it_returns_for_a_listening_socket(through: Container, log: Path) -> None:
        await through.exec("sh", "-c", f"{LISTEN} >/dev/null 2>&1 &")
        await asyncio.wait_for(wait_for_socket(through, SOCKET, client(through), log, 10), 10)

    async def it_times_out_on_a_path_that_never_shows_up(through: Container, log: Path) -> None:
        with pytest.raises(RuntimeError, match="did not start:\nenvoy: starting"):
            await wait_for_socket(through, SOCKET, client(through), log, 0.3)

    async def it_waits_for_a_listener_that_starts_late(through: Container, log: Path) -> None:
        await through.exec("sh", "-c", f"(sleep 0.5; {LISTEN}) >/dev/null 2>&1 &")
        await asyncio.wait_for(wait_for_socket(through, SOCKET, client(through), log, 10), 10)

    async def it_stops_waiting_when_the_client_exits(log: Path) -> None:
        process = await asyncio.create_subprocess_exec("false")
        exited = asyncio.ensure_future(process.wait())
        missing = Container(f"botbox-test-missing-{uuid4().hex[:12]}")
        with pytest.raises(RuntimeError, match="did not start"):
            await asyncio.wait_for(wait_for_socket(missing, SOCKET, exited, log, 30), 5)
