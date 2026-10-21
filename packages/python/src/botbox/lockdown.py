import re
import subprocess
from collections.abc import Generator, Iterable
from contextlib import contextmanager, suppress
from pathlib import Path
from uuid import uuid4

from python_on_whales import docker
from python_on_whales.exceptions import DockerException

from botbox.stop_attached import stop_attached
from botbox.wait_for_socket import wait_for_socket

PROXY_DIR = Path(__file__).with_name("proxy")
PROXY_CONF = PROXY_DIR / "tinyproxy.conf"
PROXY_IMAGE = "botbox-proxy:latest"
PROXY_LOG_DIR = "/var/log/tinyproxy"
# tinyproxy's uid in the image, pinned so a rebuilt image can't drift onto the agent's.
PROXY_USER = "100:101"
# tinyproxy's threads and socat's per-connection children, at MaxClients/max-children 100 each.
PROXY_PIDS = 256
PROXY_READY_SECONDS = 30
PROXY_EXIT_SECONDS = 10
SOCKET_DIR = "/run/botbox"
RELAY_DIR = Path(__file__).with_name("relay")
RELAY = "/usr/local/bin/botbox-relay"
# Off the usual proxy ports, so the relay doesn't take one a caller's workload expects.
RELAY_PORT = 41893


class Lockdown:
    """The proxy a locked-down container shares a PID namespace with, its socket, and its log."""

    def __init__(self, proxy: str, sockets: Path, envs: dict[str, str]) -> None:
        self.proxy = proxy
        self.sockets = sockets
        self.envs = envs
        self.log = ""


@contextmanager
def lockdown(allow: Iterable[str], scratch: Path) -> Generator[Lockdown]:
    """Start the run's proxy and yield what a locked-down container needs to reach it.

    The container gets no network. Its only way out is a unix socket in `scratch`, served by
    a tinyproxy sidecar on Docker's default bridge that refuses anything outside `allow`.
    tinyproxy listens on the sidecar's loopback only, so nothing else on the bridge reaches it.

    The sidecar runs under an init and lives while this process holds its stdin. If this
    process dies however it dies, stdin closes, the init exits, and the kernel kills every
    process in the sidecar's PID namespace, which the agent container joins.
    tinyproxy writes its log into `scratch` as it runs; it is read into `Lockdown.log` on exit.
    """
    docker.build(PROXY_DIR, tags=PROXY_IMAGE, file=PROXY_DIR / "Dockerfile", progress=False)

    name = f"botbox-proxy-{uuid4().hex[:12]}"
    url = f"http://127.0.0.1:{RELAY_PORT}"
    sockets = scratch / "sockets"
    sockets.mkdir()
    # The proxy runs as its own user and creates the socket here.
    sockets.chmod(0o777)
    jail = Lockdown(
        proxy=name,
        sockets=sockets,
        envs={
            "HTTP_PROXY": url,
            "HTTPS_PROXY": url,
            "http_proxy": url,
            "https_proxy": url,
            "NO_PROXY": "localhost,127.0.0.1",
        },
    )

    allowlist = scratch / "filter"
    allowlist.write_text("".join(f"^{re.escape(host)}$\n" for host in allow))
    allowlist.chmod(0o644)
    log_dir = scratch / "proxy"
    log_dir.mkdir()
    log_dir.chmod(0o755)
    log = log_dir / "tinyproxy.log"
    log.touch()
    log.chmod(0o666)
    output = scratch / "proxy.out"

    process = None
    try:
        docker.container.create(
            PROXY_IMAGE,
            interactive=True,
            remove=True,
            init=True,
            name=name,
            user=PROXY_USER,
            networks=["bridge"],
            pids_limit=PROXY_PIDS,
            volumes=[
                (str(allowlist), "/etc/tinyproxy/filter", "ro"),
                (str(log_dir), PROXY_LOG_DIR, "rw"),
                (str(sockets), SOCKET_DIR, "rw"),
            ],
            cap_drop=["ALL"],
            security_options=["no-new-privileges"],
        )
        with output.open("w") as out:
            process = subprocess.Popen(
                ["docker", "start", "--attach", "--interactive", name],
                stdin=subprocess.PIPE,
                stdout=out,
                stderr=subprocess.STDOUT,
            )
        wait_for_socket(sockets / "proxy.sock", process, output, PROXY_READY_SECONDS)
        yield jail
    finally:
        if process is not None:
            stop_attached(process, PROXY_EXIT_SECONDS)
        # Never started, or wouldn't stop; otherwise it is already gone with --rm.
        with suppress(DockerException):
            docker.container.remove(name, force=True)
        jail.log = log.read_text()
