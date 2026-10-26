import json
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from botbox.credential_proxy.sds_secret import sds_secret


@pytest.fixture(autouse=True)
def secret_name() -> Iterator[str]:
    with patch(f"{__package__}.sds_secret.SECRET_NAME", "the-name") as name:
        yield name


def describe_sds_secret() -> None:
    def it_holds_the_value_under_the_name_the_config_reads() -> None:
        (resource,) = json.loads(sds_secret("Bearer token"))["resources"]
        assert resource == {
            "@type": "type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret",
            "name": "the-name",
            "generic_secret": {"secret": {"inline_string": "Bearer token"}},
        }

    def it_escapes_the_value() -> None:
        (resource,) = json.loads(sds_secret('a"b\n'))["resources"]
        assert resource["generic_secret"]["secret"]["inline_string"] == 'a"b\n'
