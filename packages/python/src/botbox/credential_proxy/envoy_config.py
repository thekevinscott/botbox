import json
from dataclasses import dataclass
from pathlib import Path

TEMPLATE = Path(__file__).with_name("envoy.json")
# The config is checked against this release.
IMAGE = (
    "envoyproxy/envoy:v1.36.2"
    "@sha256:4972515dd9a069b44beb43cebba7851596e72a8c61cd7a7c33d8f48efc5280ba"
)
# A tmpfs in the proxy's container, so the secret never reaches a disk or the agent's mounts.
SECRET_DIR = "/run/credentials"
SECRET_FILE = f"{SECRET_DIR}/secret.json"
SECRET_NAME = "upstream"


@dataclass(frozen=True)
class Injection:
    """A credential the proxy adds to the requests it forwards to one HTTPS host."""

    upstream: str
    """The host, reached over TLS on 443 and checked against its certificate."""
    paths: str
    """An RE2 regex the whole path, without its query, must match. Other paths get a 403."""
    header: str
    """The header the proxy sets to the secret, replacing the client's own."""
    strip: tuple[str, ...] = ()
    """More client headers to drop, such as the auth header the upstream doesn't expect."""


def envoy_config(injection: Injection, socket: str) -> str:
    """Envoy's bootstrap as JSON, for `--config-yaml`, serving `injection` on the unix `socket`.

    Envoy reads the secret from `SECRET_FILE`, which must exist before it starts, and takes a
    new one when a file is renamed over it. Writing the file in place goes unnoticed.
    """
    values: dict[str, str | list[str]] = {
        "__SOCKET__": socket,
        "__UPSTREAM__": injection.upstream,
        "__PATHS__": injection.paths,
        "__HEADER__": injection.header,
        "__STRIP__": list(injection.strip),
        "__SECRET_NAME__": SECRET_NAME,
        "__SECRET_FILE__": SECRET_FILE,
        "__SECRET_DIR__": SECRET_DIR,
    }
    text = TEMPLATE.read_text()
    for placeholder, value in values.items():
        text = text.replace(json.dumps(placeholder), json.dumps(value))
    return json.dumps(json.loads(text), separators=(",", ":"))
