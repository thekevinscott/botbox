import pytest

from botbox.authority import authority


def describe_authority() -> None:
    @pytest.mark.parametrize(
        ("host", "expected"),
        [
            ("2001:db8::1", "[2001:db8::1]"),
            ("::1", "[::1]"),
            ("192.0.2.1", "192.0.2.1"),
            ("api.anthropic.com", "api.anthropic.com"),
        ],
    )
    def it_brackets_only_an_ipv6_literal(host: str, expected: str) -> None:
        assert authority(host) == expected
