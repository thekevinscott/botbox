import json

from botbox.credential_proxy.envoy_config import SECRET_NAME
from botbox.credential_proxy.sds_secret import sds_secret


def describe_sds_secret() -> None:
    def it_holds_the_value_under_the_name_the_config_reads() -> None:
        (resource,) = json.loads(sds_secret("Bearer token"))["resources"]
        assert resource == {
            "@type": "type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret",
            "name": SECRET_NAME,
            "generic_secret": {"secret": {"inline_string": "Bearer token"}},
        }

    def it_escapes_the_value() -> None:
        (resource,) = json.loads(sds_secret('a"b\n'))["resources"]
        assert resource["generic_secret"]["secret"]["inline_string"] == 'a"b\n'
