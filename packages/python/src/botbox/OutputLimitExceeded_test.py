from botbox.OutputLimitExceeded import OutputLimitExceeded


def describe_OutputLimitExceeded() -> None:
    def it_is_an_exception_with_its_message() -> None:
        error = OutputLimitExceeded("too long")
        assert isinstance(error, Exception)
        assert str(error) == "too long"
