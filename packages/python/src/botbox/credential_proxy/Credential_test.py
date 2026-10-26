from botbox.credential_proxy.Credential import Credential
from botbox.credential_proxy.envoy_config import Injection


def describe_Credential() -> None:
    def it_keeps_the_secret_out_of_its_repr() -> None:
        credential = Credential(Injection("h", "/p", "Authorization"), "Bearer hidden")
        assert "hidden" not in repr(credential)
        assert credential.secret == "Bearer hidden"
