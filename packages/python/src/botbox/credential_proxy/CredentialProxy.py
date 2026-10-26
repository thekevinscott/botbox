import asyncio
import os
from pathlib import Path

from adocker import DockerException
from adocker.Capture import Capture
from adocker.execute import execute
from botbox.credential_proxy.envoy_config import SECRET_FILE
from botbox.credential_proxy.preloaded import preloaded
from botbox.credential_proxy.sds_secret import sds_secret

# Envoy only notices a file renamed over the secret.
ROTATE = 'cat >"$1.next" && mv "$1.next" "$1"'


class CredentialProxy:
    """A running credential proxy: its container and the socket it serves."""

    def __init__(self, name: str, socket: Path) -> None:
        self.name = name
        self.socket = socket

    async def rotate(self, value: str) -> None:
        """Have the proxy send `value` from its next request on. Raises DockerException."""
        args = ["exec", "--interactive", self.name, "sh", "-c", ROTATE, "sh", SECRET_FILE]
        stdin = preloaded(sds_secret(value))
        err = bytearray()
        try:
            async with Capture(err) as stderr:
                code = await execute(
                    args, stdin=stdin, stdout=asyncio.subprocess.DEVNULL, stderr=stderr
                )
        finally:
            os.close(stdin)
        if code != 0:
            raise DockerException(["docker", *args], code, err.decode(errors="replace"))
