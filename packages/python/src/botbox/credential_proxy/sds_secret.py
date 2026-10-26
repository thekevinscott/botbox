import json

from botbox.credential_proxy.envoy_config import SECRET_NAME


def sds_secret(value: str) -> bytes:
    """The SDS file Envoy reads the header's whole `value` from, such as `Bearer <token>`."""
    secret = {
        "@type": "type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret",
        "name": SECRET_NAME,
        "generic_secret": {"secret": {"inline_string": value}},
    }
    return json.dumps({"resources": [secret]}).encode()
