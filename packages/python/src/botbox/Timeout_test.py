from unittest.mock import sentinel

import pytest

from botbox.Timeout import Timeout

RESULT = sentinel.result


def describe_timeout() -> None:
    def it_is_a_timeout_error() -> None:
        with pytest.raises(TimeoutError):
            raise Timeout(30, RESULT)

    def it_holds_what_the_run_left() -> None:
        assert Timeout(30, RESULT).result is RESULT

    def it_holds_the_limit() -> None:
        assert Timeout(2.5, RESULT).seconds == 2.5

    def it_says_how_long_it_ran() -> None:
        assert str(Timeout(2.5, RESULT)) == "botbox stopped the agent after its 2.5s timeout"
