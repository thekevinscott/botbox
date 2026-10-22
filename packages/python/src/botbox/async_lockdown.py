import asyncio
import os
import re
import warnings
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from pathlib import Path

from botbox.async_build_lock import async_build_lock
from botbox.authority import authority
from botbox.docker.build import build
from botbox.docker.run import run
from botbox.docker.settle import settle
from botbox.lockdown import (
    PROXY_DIR,
    PROXY_EXIT_SECONDS,
    PROXY_IMAGE,
    PROXY_LOG_DIR,
    PROXY_PIDS,
    PROXY_READY_SECONDS,
    PROXY_USER,
    RELAY_PORT,
    SOCKET_DIR,
    Lockdown,
)
from botbox.owner_only import owner_only
from botbox.stop_proxy import stop_proxy
from botbox.wait_for_proxy import wait_for_proxy

OUTPUT_LIMIT = 64 * 1024


@asynccontextmanager
async def async_lockdown(
    allow: Iterable[str], scratch: Path, token: str
) -> AsyncIterator[Lockdown]:
    """`lockdown` for asyncio: start the run's proxy and yield what a locked-down container needs.

    The same proxy, tethered the same way: an attached `docker run` that lives while this
    process holds its stdin. It doesn't remove itself. Leaving the block closes its stdin and
    removes it, through any number of cancels. An owner killed outright leaves it stopped,
    labelled `botbox.run=<token>`. The last 64 KiB of its output is the error if it won't start.
    """
    async with async_build_lock(PROXY_IMAGE):
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
    log_dir = scratch / "proxy"
    log_dir.mkdir()
    log_dir.chmod(0o755)
    log = log_dir / "tinyproxy.log"
    log.touch()
    log.chmod(0o666)

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
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--volume",
        f"{allowlist}:/etc/tinyproxy/filter:ro",
        "--volume",
        f"{log_dir}:{PROXY_LOG_DIR}:rw",
        "--volume",
        f"{sockets}:{SOCKET_DIR}:rw",
        PROXY_IMAGE,
    ]
    output = bytearray()
    # Created here, not by the spawn, so the write end is owner-only before any fork can copy it.
    read, write = os.pipe()
    stdin = os.fdopen(write, "wb")
    try:
        with owner_only(stdin):
            client = asyncio.ensure_future(
                run(args, stdin=read, stdout=output, stderr=output, limit=OUTPUT_LIMIT)
            )
            try:
                await wait_for_proxy(sockets / "proxy.sock", client, output, PROXY_READY_SECONDS)
                yield jail
            finally:
                await settle(stop_proxy(client, stdin, name, PROXY_EXIT_SECONDS))
    finally:
        os.close(read)
        try:
            jail.log = log.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            # 3: past contextlib's __aexit__, to whoever entered the block.
            warnings.warn(
                f"botbox could not read its proxy log: {error}", RuntimeWarning, stacklevel=3
            )
