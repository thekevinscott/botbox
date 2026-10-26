import asyncio
import os
import time
import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

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
from botbox.docker.remove import remove
from botbox.docker.run import run
from botbox.docker.run_docker import run_docker
from posix_tools.process import settle

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
STOP_SECONDS = 5
REMOVE_SECONDS = 30
POLL = 0.05
ERROR_BYTES = 64 * 1024


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
                await wait_for_socket(socket, client, log)
                yield CredentialProxy(name, socket)
            finally:
                await settle(stop(client, name))
    finally:
        os.close(stdin)


async def wait_for_socket(socket: Path, client: asyncio.Future[int], log: Path) -> None:
    """Return once `socket` accepts a connection, which can come a moment after it exists."""
    deadline = time.monotonic() + READY_SECONDS
    while True:
        try:
            _, writer = await asyncio.open_unix_connection(socket)
        except OSError:
            pass
        else:
            writer.close()
            await writer.wait_closed()
            return
        if client.done() or time.monotonic() > deadline:
            with log.open("rb") as output:
                output.seek(max(0, output.seek(0, os.SEEK_END) - ERROR_BYTES))
                text = output.read().decode(errors="replace")
            cause = client.exception() if client.done() else None
            raise RuntimeError(f"botbox credential proxy did not start:\n{text}") from cause
        await asyncio.sleep(POLL)


async def stop(client: asyncio.Future[int], name: str) -> None:
    """Stop the container so Envoy flushes its access log, then remove it.

    The attached client is killed if it outlives the stop.
    """
    try:
        async with asyncio.timeout(REMOVE_SECONDS):
            await run_docker("stop", "--time", str(STOP_SECONDS), name)
            await asyncio.wait({client}, timeout=STOP_SECONDS)
            client.cancel()
            await asyncio.gather(client, return_exceptions=True)
            await remove(name)
    except Exception as error:
        warnings.warn(
            f"botbox could not remove its credential proxy {name}: {error}",
            RuntimeWarning,
            stacklevel=2,
        )
