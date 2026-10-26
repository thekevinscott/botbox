import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from adocker.run import run
from botbox.credential_proxy.CredentialProxy import CredentialProxy
from botbox.credential_proxy.envoy_config import (
    IMAGE,
    SECRET_DIR,
    SECRET_FILE,
    Injection,
    envoy_config,
)
from botbox.credential_proxy.preloaded import preloaded
from botbox.credential_proxy.sds_secret import sds_secret
from botbox.credential_proxy.stop_container import stop_container
from botbox.credential_proxy.wait_for_socket import wait_for_socket
from botbox.process import settle

# envoy's uid in the image. The agent must not run as it.
USER = "101:101"
SOCKET_DIR = "/run/botbox"
SOCKET = "credentials.sock"
# Envoy refuses to start without the secret file, so it is written before envoy execs. Its
# default 10s log flush would lose the access log's tail when the PID namespace is killed.
START = (
    'cat >"$1" && exec envoy --concurrency 1 --file-flush-interval-msec 100'
    ' --log-level warn --config-yaml "$2"'
)
PIDS = 64
READY_SECONDS = 30


@asynccontextmanager
async def credential_proxy(  # noqa: PLR0913
    injection: Injection, secret: str, *, proxy: str, sockets: Path, token: str, log: Path
) -> AsyncIterator[CredentialProxy]:
    """Start an Envoy container that adds `secret` to requests for `injection`'s upstream.

    It serves `sockets/credentials.sock` and joins the container `proxy`'s PID namespace, so
    it dies with that container's init. The secret lives on a tmpfs inside it, reached only
    through its stdin. Its output goes to `log`. Leaving the block removes it; an owner
    killed outright leaves it labelled `botbox.run=<token>`.
    """
    name = f"botbox-credentials-{token}"
    socket = sockets / SOCKET
    config = envoy_config(injection, f"{SOCKET_DIR}/{SOCKET}")
    args = [
        "--interactive",
        "--name",
        name,
        "--label",
        f"botbox.run={token}",
        "--user",
        USER,
        "--pid",
        f"container:{proxy}",
        "--network",
        "bridge",
        "--pids-limit",
        str(PIDS),
        "--log-driver",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        f"{SECRET_DIR}:uid=101,gid=101,mode=0700",
        "--volume",
        f"{sockets}:{SOCKET_DIR}:rw",
        "--entrypoint",
        "sh",
        IMAGE,
        "-c",
        START,
        "sh",
        SECRET_FILE,
        config,
    ]
    stdin = preloaded(sds_secret(secret))
    try:
        with log.open("wb") as sink:
            client = asyncio.ensure_future(run(args, stdin=stdin, stdout=sink, stderr=sink))
            try:
                await wait_for_socket(socket, client, log, READY_SECONDS)
                yield CredentialProxy(name, socket)
            finally:
                await settle(stop_container(client, name))
    finally:
        os.close(stdin)
