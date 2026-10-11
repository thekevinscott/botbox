import re
from collections.abc import Generator, Iterable
from contextlib import contextmanager, suppress
from pathlib import Path
from uuid import uuid4

from python_on_whales import docker
from python_on_whales import utils as docker_utils
from python_on_whales.exceptions import DockerException

PROXY_DIR = Path(__file__).with_name("proxy")
PROXY_IMAGE = "botbox-proxy:latest"
PROXY_PORT = 8888
PROXY_LOG_DIR = "/var/log/tinyproxy"


class Lockdown:
    """The network a locked-down container joins, the proxy env it runs under, and the proxy log."""

    def __init__(self, network: str, envs: dict[str, str]) -> None:
        self.network = network
        self.envs = envs
        self.log = ""


@contextmanager
def lockdown(allow: Iterable[str], scratch: Path) -> Generator[Lockdown]:
    """Yield the network and proxy env a locked-down container runs under.

    The container joins an `--internal` network: no gateway, no route out, no external DNS.
    Its only way out is a CONNECT to the sidecar, which sits on a second network and refuses
    anything outside `allow`. tinyproxy writes its log into `scratch` on the host as it runs,
    so the log survives the daemon; it is read into `Lockdown.log` on the way out.
    """
    docker.build(PROXY_DIR, tags=PROXY_IMAGE, file=PROXY_DIR / "Dockerfile", progress=False)

    run_id = uuid4().hex[:12]
    proxy_name = f"botbox-proxy-{run_id}"
    url = f"http://{proxy_name}:{PROXY_PORT}"
    jail = Lockdown(
        network=f"botbox-jail-{run_id}",
        envs={
            "HTTP_PROXY": url,
            "HTTPS_PROXY": url,
            "http_proxy": url,
            "https_proxy": url,
            "NO_PROXY": "localhost,127.0.0.1",
        },
    )
    egress = f"botbox-egress-{run_id}"

    allowlist = scratch / "filter"
    allowlist.write_text("".join(f"^{re.escape(host)}$\n" for host in allow))
    allowlist.chmod(0o644)
    # The proxy runs as its own user with no capabilities: it needs the bits to write here.
    log_dir = scratch / "proxy"
    log_dir.mkdir()
    log_dir.chmod(0o755)
    log = log_dir / "tinyproxy.log"
    log.touch()
    log.chmod(0o666)

    proxy = None
    networks = []
    try:
        # python-on-whales' network.create wraps no --internal, and --internal is the point.
        docker_utils.run(
            [*docker.network.docker_cmd, "network", "create", "--internal", jail.network]
        )
        networks.append(jail.network)
        docker.network.create(egress)
        networks.append(egress)
        proxy = docker.run(
            PROXY_IMAGE,
            detach=True,
            name=proxy_name,
            networks=[egress],
            volumes=[
                (str(allowlist), "/etc/tinyproxy/filter", "ro"),
                (str(log_dir), PROXY_LOG_DIR, "rw"),
            ],
            cap_drop=["ALL"],
            security_options=["no-new-privileges"],
        )
        docker.network.connect(jail.network, proxy)
        yield jail
    finally:
        gone = False
        if proxy is not None:
            with suppress(DockerException):
                docker.container.remove(proxy, force=True)
                gone = True
        for network in networks:
            if proxy is not None and not gone:
                with suppress(DockerException):
                    docker.network.disconnect(network, proxy, force=True)
            with suppress(DockerException):
                docker.network.remove(network)
        jail.log = log.read_text()
