import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from adocker import Container, Image, Volume
from botbox.credential_proxy.Credential import Credential
from botbox.credential_proxy.CredentialProxy import CredentialProxy
from botbox.credential_proxy.envoy_config import (
    IMAGE,
    SECRET_DIR,
    SECRET_FILE,
    envoy_config,
)
from botbox.credential_proxy.preloaded import preloaded
from botbox.credential_proxy.sds_secret import sds_secret
from botbox.credential_proxy.stop_container import stop_container
from botbox.credential_proxy.wait_for_socket import wait_for_socket
from botbox.process import settle
from botbox.write import write

# envoy's uid in the image. The agent must not run as it.
USER = "101:101"
SOCKET_DIR = "/run/botbox"
SOCKET = f"{SOCKET_DIR}/credentials.sock"
# Envoy refuses to start without the secret file, so it is written before envoy execs. Its
# default 10s log flush would lose the access log's tail when the PID namespace is killed.
START = (
    'cat >"$1" && exec envoy --concurrency 1 --file-flush-interval-msec 100'
    ' --log-level warn --config-yaml "$2"'
)
PIDS = 64
READY_SECONDS = 30


@asynccontextmanager
async def credential_proxy(
    credential: Credential, *, proxy: Container, volume: Volume, token: str, log: Path
) -> AsyncIterator[CredentialProxy]:
    """Start an Envoy container that adds the credential's secret to requests for its upstream.

    It serves `credentials.sock` in `volume`, beside the socket of the container `proxy`, and
    joins `proxy`'s PID namespace, so it dies with that container's init. The secret lives on a
    tmpfs inside it, reached only through its stdin. Its output goes to `log`. Leaving the block
    removes it; an owner killed outright leaves it labelled `botbox.run=<token>`.
    """
    name = f"botbox-credentials-{token}"
    config = envoy_config(credential.injection, SOCKET)
    stdin = preloaded(sds_secret(credential.secret))
    try:
        with write(log) as sink:
            container = Container(name)
            try:
                container = await Image(IMAGE).run(
                    "-c",
                    START,
                    "sh",
                    SECRET_FILE,
                    config,
                    name=name,
                    stdin=stdin,
                    stdout=sink,
                    stderr=sink,
                    labels={"botbox.run": token},
                    user=USER,
                    pid=f"container:{proxy.name}",
                    network="bridge",
                    pids_limit=PIDS,
                    log_driver="none",
                    cap_drop=["ALL"],
                    security_opt=["no-new-privileges"],
                    tmpfs=[f"{SECRET_DIR}:uid=101,gid=101,mode=0700"],
                    mounts=[volume.mount(SOCKET_DIR)],
                    entrypoint="sh",
                )
                client = cast("asyncio.Task[int]", container.client)
                await wait_for_socket(proxy, SOCKET, client, log, READY_SECONDS)
                yield CredentialProxy(container, SOCKET)
            finally:
                await settle(stop_container(container))
    finally:
        os.close(stdin)
