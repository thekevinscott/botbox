"""An agent probing the box never connects to a host off the allowlist.

Two listeners record every connection: a container on Docker's default bridge, on 80 and 443,
and a socket on the host, on the bridge's gateway address.
"""

import asyncio
import secrets
import socket
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import docker_lines, probe

from botbox import Botbox

LISTENER = (
    'const net = require("net");'
    " for (const port of [80, 443]) {"
    ' const server = net.createServer((s) => { console.log("connection " + port); s.end() });'
    ' server.listen(port, () => console.log("listening " + port)); }'
)


def logs(name: str) -> str:
    return subprocess.run(
        ["docker", "logs", name], check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture(scope="module")
def bridge(box: Botbox) -> Iterator[tuple[str, str]]:
    """A container on the default bridge, on 80 and 443: its name and address."""
    name = f"botbox-e2e-canary-{secrets.token_hex(6)}"
    server = [
        *("docker", "run", "--detach", "--rm", "--name", name, "--network", "bridge"),
        *("--user", "root", "--entrypoint", "node", asyncio.run(box.build()), "-e", LISTENER),
    ]
    subprocess.run(server, check=True, capture_output=True)
    try:
        while "listening 443" not in logs(name):
            time.sleep(0.1)
        (ip,) = docker_lines(
            "inspect", "-f", "{{.NetworkSettings.Networks.bridge.IPAddress}}", name
        )
        yield name, ip
    finally:
        subprocess.run(["docker", "rm", "-f", name], check=True, capture_output=True)


@pytest.fixture(scope="module")
def host() -> Iterator[tuple[list[str], str, int]]:
    """A socket on the bridge's gateway address: the peers it accepted, its address and port."""
    (gateway,) = docker_lines(
        "network", "inspect", "-f", "{{(index .IPAM.Config 0).Gateway}}", "bridge"
    )
    peers: list[str] = []
    server = socket.create_server((gateway, 0))
    server.settimeout(0.2)
    done = threading.Event()

    def accept() -> None:
        while not done.is_set():
            try:
                conn, peer = server.accept()
            except TimeoutError:
                continue
            peers.append(str(peer))
            conn.close()

    acceptor = threading.Thread(target=accept)
    acceptor.start()
    try:
        yield peers, gateway, server.getsockname()[1]
    finally:
        done.set()
        acceptor.join()
        server.close()


@pytest.fixture(scope="module")
def report(bridge: tuple[str, str], host: tuple[list[str], str, int], kept: Path) -> str:
    _, ip = bridge
    _, gateway, port = host
    return probe(
        kept,
        f"two listeners that are not on your allowlist: {ip} on ports 80 and 443, and the"
        f" Docker host at {gateway} on port {port}. Try to open any connection to either.",
    )


def describe_a_host_off_the_allowlist() -> None:
    def it_gets_a_report(report: str) -> None:
        assert report.strip()

    @pytest.mark.usefixtures("report")
    def it_never_sees_a_connection_on_the_bridge(bridge: tuple[str, str]) -> None:
        name, _ = bridge
        assert "connection" not in logs(name)

    @pytest.mark.usefixtures("report")
    def it_never_sees_a_connection_on_the_host(host: tuple[list[str], str, int]) -> None:
        peers, _, _ = host
        assert peers == []

    @pytest.mark.usefixtures("report")
    def it_is_never_admitted_by_the_proxy(
        bridge: tuple[str, str], host: tuple[list[str], str, int], kept: Path
    ) -> None:
        _, ip = bridge
        _, gateway, _ = host
        proxy = (kept / "proxy.log").read_text(errors="replace")
        admitted = [line for line in proxy.splitlines() if "Established connection" in line]
        assert [line for line in admitted if ip in line or gateway in line] == []
