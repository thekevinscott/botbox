from pathlib import Path

from botbox.credential_proxy.CredentialProxy import CredentialProxy


def describe_CredentialProxy() -> None:
    def it_holds_its_name_and_socket() -> None:
        proxy = CredentialProxy("botbox-credentials-1", Path("/s/c.sock"))
        assert proxy.name == "botbox-credentials-1"
        assert proxy.socket == Path("/s/c.sock")
