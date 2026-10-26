import os

from adocker import Container
from botbox.credential_proxy.envoy_config import SECRET_FILE
from botbox.credential_proxy.preloaded import preloaded
from botbox.credential_proxy.sds_secret import sds_secret

# Envoy only notices a file renamed over the secret.
ROTATE = 'cat >"$1.next" && mv "$1.next" "$1"'


class CredentialProxy:
    """A running credential proxy: its container and the socket it serves, as a path in the
    containers that mount the run's volume."""

    def __init__(self, container: Container, socket: str) -> None:
        self.container = container
        self.socket = socket

    async def rotate(self, value: str) -> None:
        """Have the proxy send `value` from its next request on. Raises DockerException."""
        stdin = preloaded(sds_secret(value))
        try:
            await self.container.exec("sh", "-c", ROTATE, "sh", SECRET_FILE, stdin=stdin)
        finally:
            os.close(stdin)
