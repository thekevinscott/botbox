import pytest

from botbox.check_timeout import check_timeout


def describe_check_timeout() -> None:
    @pytest.mark.parametrize("seconds", [None, 0.01, 30])
    def it_returns_no_limit_or_a_positive_limit(seconds: float | None) -> None:
        assert check_timeout(seconds) == seconds

    @pytest.mark.parametrize("seconds", [0, -1, -0.5])
    def it_refuses_a_limit_that_is_not_positive(seconds: float) -> None:
        with pytest.raises(ValueError, match=rf"^timeout is in seconds .*: {seconds}$"):
            check_timeout(seconds)
