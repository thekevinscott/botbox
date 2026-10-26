from botbox.credential_proxy.Credential import Credential

INJECTION: object = object()


def describe_Credential() -> None:
    def it_keeps_the_secret_out_of_its_repr() -> None:
        credential = Credential(INJECTION, "Bearer hidden")  # type: ignore[arg-type]
        assert "hidden" not in repr(credential)
        assert credential.secret == "Bearer hidden"
