"""The Docker daemon going away mid-run, from botbox's side.

Killing the host's dockerd would take every other container with it, so the daemon goes
away the way a client sees it: botbox talks to Docker through a unix-socket relay to the
real daemon, and the relay is cut while the command runs. Every docker call after that
fails as it would against a dead daemon. The real daemon keeps running, and the test
removes what botbox could not.
"""

import asyncio
import socket
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path

import pytest
from conftest import docker_lines, leftovers

from botbox import Botbox, DockerException

DOCKER_SOCKET = "/var/run/docker.sock"


class Relay:
    """A unix socket forwarding every connection to the real Docker socket, until cut."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(path))
        self.server.listen()
        self.sockets: list[socket.socket] = []
        threading.Thread(target=self.accept, daemon=True).start()

    def accept(self) -> None:
        while True:
            try:
                client, _ = self.server.accept()
            except OSError:
                return
            daemon = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            daemon.connect(DOCKER_SOCKET)
            self.sockets += [client, daemon]
            threading.Thread(target=pump, args=(client, daemon), daemon=True).start()
            threading.Thread(target=pump, args=(daemon, client), daemon=True).start()

    def cut(self) -> None:
        for s in [self.server, *self.sockets]:
            with suppress(OSError):
                s.shutdown(socket.SHUT_RDWR)
            s.close()


def pump(source: socket.socket, sink: socket.socket) -> None:
    try:
        while data := source.recv(65536):
            sink.sendall(data)
        # Pass a half-close on: the credential sidecar's attached stdin ends with one.
        sink.shutdown(socket.SHUT_WR)
    except OSError:
        pass


def cut_when_running(relay: Relay) -> None:
    """Cut the relay once the agent container is up and its output is being followed."""
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        running = docker_lines("ps", "--filter", "ancestor=botbox-claude:latest", "-q")
        if running:
            time.sleep(2)
            relay.cut()
            return
        time.sleep(0.2)


@pytest.fixture(scope="module")
def output(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("daemon")


@pytest.fixture(scope="module")
def raised(box: Botbox, output: Path) -> Iterator[DockerException]:
    before = leftovers()
    with (
        tempfile.TemporaryDirectory(prefix="relay-") as directory,
        pytest.MonkeyPatch.context() as monkeypatch,
    ):
        relay = Relay(Path(directory) / "docker.sock")
        monkeypatch.setenv("DOCKER_HOST", f"unix://{relay.path}")
        threading.Thread(target=cut_when_running, args=(relay,), daemon=True).start()
        try:
            with (
                pytest.warns(RuntimeWarning, match="^botbox could not remove"),
                pytest.raises(DockerException) as raised,
            ):
                asyncio.run(box.run("echo started; sleep 60; echo finished", output=output))
            yield raised.value
        finally:
            relay.cut()
            monkeypatch.delenv("DOCKER_HOST")
            # Containers first: a network or volume cannot go while the proxy still uses it.
            for kind in ("container", "network", "volume"):
                for leftover in leftovers() - before:
                    if leftover.startswith(f"{kind} "):
                        subprocess.run(["docker", kind, "rm", "-f", leftover.split()[1]])


def describe_the_daemon_dying_mid_run() -> None:
    def it_raises_with_the_agents_docker_run(raised: DockerException) -> None:
        assert raised.docker_command[:2] == ["docker", "run"]

    @pytest.mark.usefixtures("raised")
    def it_keeps_the_output_that_arrived(output: Path) -> None:
        assert (output / "stdout.txt").read_text() == "started\n"

    @pytest.mark.usefixtures("raised")
    def it_keeps_the_proxy_log(output: Path) -> None:
        assert "Starting main loop" in (output / "proxy.log").read_text(errors="replace")
