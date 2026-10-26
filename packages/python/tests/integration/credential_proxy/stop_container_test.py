"""stop_container against real containers, Envoy among them."""

import asyncio
import os
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from adocker import Container, Image, Mount
from botbox.credential_proxy import Injection, envoy_config, sds_secret
from botbox.credential_proxy.envoy_config import IMAGE, SECRET_DIR, SECRET_FILE
from botbox.credential_proxy.stop_container import stop_container
from botbox.write import write

INJECTION = Injection("api.anthropic.com", "/v1/messages", "Authorization")
# Envoy's default flush, so only a clean exit gets the last access log lines out.
ENVOY = 'cat >"$1" && exec envoy --concurrency 1 --log-level warn --config-yaml "$2"'


def exists(name: str) -> bool:
    found = subprocess.run(
        ["docker", "ps", "--all", "--quiet", "--filter", f"name=^{name}$"],
        check=True,
        capture_output=True,
        text=True,
    )
    return bool(found.stdout.strip())


@asynccontextmanager
async def started(*command: str, log: Path, **options: Any) -> AsyncIterator[Container]:
    """An attached run of the Envoy image with the secret on stdin and its output in `log`."""
    name = f"botbox-test-{uuid4().hex[:12]}"
    stdin, write_end = os.pipe()
    os.write(write_end, sds_secret("Bearer one"))
    os.close(write_end)
    try:
        with write(log) as sink:
            yield await Image(IMAGE).run(
                *command,
                name=name,
                stdin=stdin,
                stdout=sink,
                stderr=sink,
                entrypoint="sh",
                **options,
            )
    finally:
        os.close(stdin)
        subprocess.run(["docker", "rm", "--force", name], capture_output=True, check=False)


async def listening(socket: Path) -> None:
    while True:
        try:
            _, writer = await asyncio.open_unix_connection(socket)
        except OSError:
            await asyncio.sleep(0.05)
        else:
            writer.close()
            return


def request(socket: Path, path: str) -> None:
    subprocess.run(
        ["curl", "-sS", "--unix-socket", str(socket), f"http://localhost{path}"],
        check=True,
        capture_output=True,
        timeout=30,
    )


def describe_stop_container() -> None:
    async def it_keeps_envoys_last_access_log_lines(tmp_path: Path) -> None:
        sockets = tmp_path / "sockets"
        sockets.mkdir()
        sockets.chmod(0o777)
        log = tmp_path / "envoy.log"
        async with started(
            "-c",
            ENVOY,
            "sh",
            SECRET_FILE,
            envoy_config(INJECTION, "/run/botbox/credentials.sock"),
            log=log,
            user="101:101",
            network="none",
            tmpfs=[f"{SECRET_DIR}:uid=101,gid=101,mode=0700"],
            mounts=[Mount("bind", str(sockets), "/run/botbox")],
        ) as container:
            await asyncio.wait_for(listening(sockets / "credentials.sock"), 60)
            for n in range(3):
                await asyncio.to_thread(request, sockets / "credentials.sock", f"/refused/{n}")
            await stop_container(container)
        lines = [line for line in log.read_text().splitlines() if " 403 " in line]
        assert [line.split()[2] for line in lines] == ["/refused/0", "/refused/1", "/refused/2"]
        assert container.client is not None
        assert container.client.done()
        assert not exists(container.name)

    async def it_kills_a_container_that_ignores_sigterm(tmp_path: Path) -> None:
        script = 'trap "" TERM; echo ready; while :; do sleep 1; done'
        log = tmp_path / "log"
        async with started("-c", script, log=log) as container:
            while b"ready" not in log.read_bytes():
                await asyncio.sleep(0.05)
            loop = asyncio.get_running_loop()
            began = loop.time()
            await stop_container(container)
        assert 5 <= loop.time() - began < 20
        assert container.client is not None
        assert container.client.done()
        assert not exists(container.name)

    async def it_warns_for_a_missing_container() -> None:
        with pytest.warns(RuntimeWarning, match="could not remove its credential proxy"):
            await stop_container(Container(f"botbox-test-missing-{uuid4().hex[:12]}"))
