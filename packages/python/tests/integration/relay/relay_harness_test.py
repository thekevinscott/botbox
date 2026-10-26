"""Runs botbox-relay in a container, beside a stand-in proxy. Named `_test` so the checks
treat it as test code.
"""

import asyncio
import contextlib
import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import uuid4

from adocker import Container, Image, Mount, Volume
from botbox.lockdown import PROXY_USER, RELAY, SOCKET_DIR

# Without cloexec the relay's orphaned socat inherits kcov's trace fd, and kcov never exits.
KCOV_COMMAND = ("kcov", "--bash-tracefd-cloexec", "--bash-dont-parse-binary-dir")
SERVE = 'socat UNIX-LISTEN:{dir}/{name}.sock,fork,mode=666 SYSTEM:"echo {name}" &'


@dataclass(frozen=True)
class Exit:
    code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class Proxy:
    """A running stand-in proxy: its container, and the volume its sockets are in."""

    container: Container
    sockets: Volume


class Relay:
    """botbox-relay in `image`, its runs measured into `coverage` when given."""

    def __init__(self, image: Image, coverage: Volume | None) -> None:
        self.image = image
        self.coverage = coverage

    async def run(
        self,
        proxy: Proxy,
        *command: str,
        user: str,
        env: dict[str, str] | None = None,
        mounts: Sequence[Mount] = (),
        stdin: bytes = b"",
    ) -> Exit:
        name = f"botbox-relay-test-{uuid4().hex[:12]}"
        argv: tuple[str, ...] = (RELAY, *command)
        if self.coverage is not None:
            argv = (*KCOV_COMMAND, f"/cov/{name}", *argv)
            mounts = [*mounts, self.coverage.mount("/cov")]
        stdout, stderr = bytearray(), bytearray()
        container = await self.image.run(
            *argv,
            name=name,
            rm=True,
            user=user,
            env=env,
            mounts=[proxy.sockets.mount(SOCKET_DIR), *mounts],
            network="none",
            pid=f"container:{proxy.container.name}",
            stdin=asyncio.subprocess.PIPE if stdin else asyncio.subprocess.DEVNULL,
            stdout=stdout.extend,
            stderr=stderr.extend,
        )
        if container.stdin is not None:
            container.stdin.write(stdin)
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                await container.stdin.drain()
            container.stdin.close()
        code = await asyncio.wait_for(container.wait(), 60)
        return Exit(code, stdout.decode(), stderr.decode())


async def uncovered_lines(image: Image, coverage: Volume) -> list[str]:
    """The relay's lines no run reached, merged across every run in `coverage`."""
    report = bytearray()
    merge = "kcov --merge /tmp/merged /cov/*/ && cat /tmp/merged/kcov-merged/cobertura.xml"
    container = await image.run(
        "sh",
        "-c",
        merge,
        name=f"botbox-relay-coverage-{uuid4().hex[:12]}",
        rm=True,
        mounts=[coverage.mount("/cov", read_only=True)],
        stdout=report.extend,
    )
    assert await container.wait() == 0
    lines = ET.fromstring(report.decode()).iter("line")
    return [line.attrib["number"] for line in lines if line.attrib["hits"] == "0"]


@asynccontextmanager
async def serving(image: Image, *names: str) -> AsyncIterator[Proxy]:
    """A container as the proxy's uid, serving each named socket with a reply of its name."""
    token = uuid4().hex[:12]
    serve = "".join(SERVE.format(dir=SOCKET_DIR, name=name) for name in names)
    ready = " && ".join(f"[ -S {SOCKET_DIR}/{name}.sock ]" for name in names)
    script = f"{serve} until {ready}; do sleep 0.05; done; echo ready; exec sleep infinity"
    up = asyncio.Event()
    async with Volume(f"botbox-relay-test-{token}") as sockets:
        container = await image.run(
            "sh",
            "-c",
            script,
            name=f"botbox-relay-proxy-{token}",
            user=PROXY_USER,
            network="none",
            mounts=[sockets.mount(SOCKET_DIR)],
            stdout=lambda _: up.set(),
        )
        try:
            await asyncio.wait_for(up.wait(), 30)
            yield Proxy(container, sockets)
        finally:
            await container.remove()
            await container.wait()
