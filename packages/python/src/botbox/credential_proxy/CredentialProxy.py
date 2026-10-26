import asyncio
import os
import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from adocker import Container, DockerException
from botbox.credential_proxy.CredentialsExpired import CredentialsExpired
from botbox.credential_proxy.CredentialSource import CredentialSource
from botbox.credential_proxy.envoy_config import SECRET_FILE
from botbox.credential_proxy.preloaded import preloaded
from botbox.credential_proxy.sds_secret import sds_secret

# Envoy only notices a file renamed over the secret.
ROTATE = 'cat >"$1.next" && mv "$1.next" "$1"'
FOLLOW_SECONDS = 2.0


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

    async def follow(self, source: CredentialSource, sent: str) -> None:
        """Rotate to `source`'s secret whenever it differs from the one last sent, until cancelled.

        `sent` is the secret the proxy started with. One that can't be read, has expired or
        can't be sent is tried again on the next check: botbox never refreshes a login, so it
        waits for the host to.
        """
        while True:
            await asyncio.sleep(FOLLOW_SECONDS)
            try:
                secret = (await asyncio.to_thread(source.read)).secret
                if secret != sent:
                    await self.rotate(secret)
                    sent = secret
            except (OSError, ValueError, CredentialsExpired, DockerException):
                continue

    @asynccontextmanager
    async def following(self, source: CredentialSource, sent: str) -> AsyncIterator[None]:
        """`follow` `source` for the length of the block. A follow that failed is warned about
        when the block ends."""
        task = asyncio.create_task(self.follow(source, sent))
        try:
            yield
        finally:
            task.cancel()
            await asyncio.wait({task})
            if not task.cancelled() and (error := task.exception()) is not None:
                warnings.warn(
                    f"botbox stopped sending the host's new credentials: {error!r}",
                    RuntimeWarning,
                    stacklevel=1,
                )
