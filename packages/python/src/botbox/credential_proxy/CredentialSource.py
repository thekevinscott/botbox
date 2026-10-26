from collections.abc import Mapping
from typing import Protocol

from botbox.credential_proxy.Credential import Credential

# Where the box reaches the proxy: botbox-relay's loopback port.
PROXY_URL = "http://127.0.0.1:41894"


class CredentialSource(Protocol):
    """A credential on the host that the proxy sends upstream, so the box holds a placeholder."""

    @property
    def env(self) -> Mapping[str, str]:
        """Environment that points the box's CLI at `PROXY_URL`."""
        ...

    def read(self) -> Credential:
        """The credential as the host holds it now. Raises `CredentialsExpired`, `OSError`, or
        `ValueError` for one it can't parse."""
        ...
