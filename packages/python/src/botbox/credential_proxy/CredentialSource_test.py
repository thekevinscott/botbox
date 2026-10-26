from collections.abc import Mapping
from typing import get_type_hints

from botbox.credential_proxy.CredentialSource import PROXY_URL, CredentialSource


def describe_CredentialSource() -> None:
    def it_gives_the_box_its_environment() -> None:
        hints = get_type_hints(CredentialSource.env.fget)  # type: ignore[attr-defined]
        assert hints == {"return": Mapping[str, str]}

    def it_reads_the_credential() -> None:
        returns = get_type_hints(CredentialSource.read)["return"]
        assert (returns.__module__, returns.__name__) == (
            "botbox.credential_proxy.Credential",
            "Credential",
        )

    def it_is_reached_on_the_relays_loopback_port() -> None:
        assert PROXY_URL == "http://127.0.0.1:41894"
