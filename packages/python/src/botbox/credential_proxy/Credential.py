from dataclasses import dataclass, field

from botbox.credential_proxy.envoy_config import Injection


@dataclass(frozen=True)
class Credential:
    """A secret and the injection that sends it upstream."""

    injection: Injection
    secret: str = field(repr=False)
