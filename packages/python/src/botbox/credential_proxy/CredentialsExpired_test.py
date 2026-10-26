from datetime import UTC, datetime
from pathlib import Path

from botbox.credential_proxy.CredentialsExpired import CredentialsExpired

EXPIRED = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def describe_CredentialsExpired() -> None:
    def it_keeps_the_login_and_when_it_expired() -> None:
        error = CredentialsExpired(Path("/h/.credentials.json"), EXPIRED)
        assert (error.path, error.expired) == (Path("/h/.credentials.json"), EXPIRED)

    def it_says_where_and_when_and_what_to_do() -> None:
        assert str(CredentialsExpired(Path("/h/.credentials.json"), EXPIRED)) == (
            "the login in /h/.credentials.json expired at 2026-10-26T12:00:00+00:00:"
            " use the CLI on the host to refresh it, then run again"
        )
