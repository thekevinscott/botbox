import asyncio
import os
import re
import warnings
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from botbox.authority import authority
from botbox.build_lock import build_lock
from botbox.docker.build import build
from botbox.docker.run import run
from botbox.process import owner_only, settle
from botbox.stop_proxy import stop_proxy
from botbox.wait_for_proxy import wait_for_proxy

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


class Lockdown:
    """The proxy a locked-down container shares a PID namespace with, its socket, and its log."""

    def __init__(self, proxy: str, sockets: Path, envs: dict[str, str]) -> None:
        self.proxy = proxy
        self.sockets = sockets
        self.envs = envs
        self.log = ""


@asynccontextmanager
async def lockdown(
    allow: Iterable[str], scratch: Path, token: str, output: Path | None = None
) -> AsyncIterator[Lockdown]:
    """Start the run's proxy and yield what a locked-down container needs to reach it.

    The container gets no network. Its only way out is a unix socket in `scratch`, served by
    a tinyproxy sidecar on Docker's default bridge that refuses anything outside `allow`.
    tinyproxy listens on the sidecar's loopback only, so nothing else on the bridge reaches it.

    The sidecar runs under an init, attached, and lives while this process holds its stdin,
    which children forked meanwhile close. When stdin closes the init exits, and the kernel
    kills every process in the sidecar's PID namespace, which the agent joins. It doesn't
    remove itself: leaving the block closes its stdin and removes it, through any number of
    cancels. An owner killed outright leaves it stopped, labelled `botbox.run=<token>`.

    All of the sidecar's output goes straight to `output/proxy.log`, which stays after exit.
    The last 64 KiB of it is the error if it won't start. Without `output` it goes to
    `scratch/proxy.log` instead, read into `Lockdown.log` on exit.
    """
    async with build_lock(PROXY_IMAGE):
        await build(PROXY_DIR, tag=PROXY_IMAGE, file=PROXY_DIR / "Dockerfile")

    name = f"botbox-proxy-{token}"
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
    # CONNECT's URL is `host:port`; plain HTTP's is `http://host[:port]/path`.
    authorities = (re.escape(authority(host)) for host in allow)
    allowlist.write_text("".join(f"^{a}(:443)?$\n^http://{a}(:80)?(/|$)\n" for a in authorities))
    allowlist.chmod(0o644)
    log = (scratch if output is None else output) / "proxy.log"

    args = [
        "--interactive",
        "--init",
        "--name",
        name,
        "--label",
        f"botbox.run={token}",
        "--user",
        PROXY_USER,
        "--network",
        "bridge",
        "--pids-limit",
        str(PROXY_PIDS),
        "--log-driver",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--volume",
        f"{allowlist}:/etc/tinyproxy/filter:ro",
        "--volume",
        f"{sockets}:{SOCKET_DIR}:rw",
        PROXY_IMAGE,
    ]
    # Created here, not by the spawn, so the write end is owner-only before any fork can copy it.
    read, write = os.pipe()
    stdin = os.fdopen(write, "wb")
    try:
        with owner_only(stdin), log.open("wb") as sink:
            client = asyncio.ensure_future(run(args, stdin=read, stdout=sink, stderr=sink))
            try:
                await wait_for_proxy(sockets / "proxy.sock", client, log, PROXY_READY_SECONDS)
                yield jail
            finally:
                await settle(stop_proxy(client, stdin, name, PROXY_EXIT_SECONDS))
    finally:
        with suppress(OSError):
            stdin.close()
        os.close(read)
        if output is None:
            try:
                jail.log = log.read_text(encoding="utf-8", errors="replace")
            except OSError as error:
                # 3: past contextlib's __aexit__, to whoever entered the block.
                warnings.warn(
                    f"botbox could not read its proxy log: {error}", RuntimeWarning, stacklevel=3
                )
