import asyncio
import re
import warnings
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from adocker import Container, Dockerfile, Volume
from botbox.authority import authority
from botbox.credential_proxy import Credential, CredentialProxy, credential_proxy
from botbox.process import settle
from botbox.stop_proxy import stop_proxy
from botbox.wait_for_proxy import wait_for_proxy
from botbox.write import write

PROXY_DIR = Path(__file__).with_name("proxy")
PROXY_CONF = PROXY_DIR / "tinyproxy.conf"
PROXY_IMAGE = "botbox-proxy:latest"
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
# Tells the relay the run asked for injection, so a missing credential socket is an error.
CREDENTIALS_ENV = "BOTBOX_CREDENTIALS"


class Lockdown:
    """The proxy a locked-down container shares a PID namespace with, and the volume holding its
    socket."""

    def __init__(
        self,
        proxy: Container,
        volume: Volume,
        envs: dict[str, str],
        credentials: CredentialProxy | None = None,
    ) -> None:
        self.proxy = proxy
        self.volume = volume
        self.envs = envs
        self.credentials = credentials


@asynccontextmanager
async def lockdown(
    allow: Iterable[str],
    scratch: Path,
    token: str,
    output: Path | None = None,
    *,
    credential: Credential | None = None,
) -> AsyncIterator[Lockdown]:
    """Start the run's proxy and yield what a locked-down container needs to reach it.

    The container gets no network. Its only way out is a unix socket in the run's volume, served
    by a tinyproxy sidecar on Docker's default bridge that refuses anything outside `allow`.
    tinyproxy listens on the sidecar's loopback only, so nothing else on the bridge reaches it.

    The sidecar runs under an init, attached, and lives while this process holds its stdin,
    which only this process holds. When stdin closes the init exits, and the kernel
    kills every process in the sidecar's PID namespace, which the agent joins. It doesn't
    remove itself: leaving the block closes its stdin and removes it, through any number of
    cancels. The volume is removed after it. An owner killed outright leaves both, the sidecar
    stopped, labelled `botbox.run=<token>`.

    The tinyproxy log goes to `scratch/proxy.log` and to `output/proxy.log` when given.
    With a `credential`, an Envoy sidecar serves it on `credentials.sock` in the same volume, and
    its output goes to `credentials.log` in `output`, or `scratch` without one.
    """
    image = await Dockerfile(PROXY_DIR / "Dockerfile").build(PROXY_IMAGE)

    name = f"botbox-proxy-{token}"
    volume = f"botbox-run-{token}"
    url = f"http://127.0.0.1:{RELAY_PORT}"
    envs = {
        "HTTP_PROXY": url,
        "HTTPS_PROXY": url,
        "http_proxy": url,
        "https_proxy": url,
        "NO_PROXY": "localhost,127.0.0.1",
    }
    if credential is not None:
        envs[CREDENTIALS_ENV] = "1"

    # CONNECT's URL is `host:port`; plain HTTP's is `http://host[:port]/path`.
    authorities = (re.escape(authority(host)) for host in allow)
    allowlist = "".join(f"^{a}(:443)?$\n^http://{a}(:80)?(/|$)\n" for a in authorities)
    log = scratch / "proxy.log"
    also = [] if output is None else [output / "proxy.log"]

    def unremoved(error: Exception) -> None:
        warnings.warn(
            f"botbox could not remove its volume {volume}: {error}", RuntimeWarning, stacklevel=1
        )

    labels = {"botbox.run": token}
    with write(log, *also) as sink:
        async with Volume(volume, labels=labels, on_error=unremoved) as socket:
            proxy = Container(name)
            try:
                proxy = await image.run(
                    name=name,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=sink,
                    stderr=sink,
                    init=True,
                    labels=labels,
                    user=PROXY_USER,
                    network="bridge",
                    pids_limit=PROXY_PIDS,
                    log_driver="none",
                    cap_drop=["ALL"],
                    security_opt=["no-new-privileges"],
                    env={"BOTBOX_FILTER": allowlist},
                    mounts=[socket.mount(SOCKET_DIR)],
                )
                await wait_for_proxy(
                    cast("asyncio.Task[int]", proxy.client), log, PROXY_READY_SECONDS
                )
                if credential is None:
                    yield Lockdown(proxy, socket, envs)
                else:
                    credential_log = (scratch if output is None else output) / "credentials.log"
                    async with credential_proxy(
                        credential, proxy=proxy, volume=socket, token=token, log=credential_log
                    ) as credentials:
                        yield Lockdown(proxy, socket, envs, credentials)
            finally:
                await settle(stop_proxy(proxy, PROXY_EXIT_SECONDS))
