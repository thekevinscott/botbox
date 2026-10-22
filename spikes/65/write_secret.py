"""Write the Envoy SDS secret the credential proxy injects, atomically.

  oauth   <.claude/.credentials.json> <dir> [--watch]   Bearer <claudeAiOauth.accessToken>
  codex   <.codex/auth.json> <dir> [--watch]            Bearer <tokens.access_token>
  apikey  <dir>                                         the key from $ANTHROPIC_API_KEY
  literal <value> <dir>                                 a fixed header value (rotation tests)

--watch rewrites the secret whenever the login file changes. It never refreshes.
"""

import base64
import json
import os
import sys
import tempfile
import time
from pathlib import Path


def write(directory: Path, value: str) -> None:
    body = {
        "resources": [
            {
                "@type": "type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret",
                "name": "upstream",
                "generic_secret": {"secret": {"inline_string": value}},
            }
        ]
    }
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".secret-")
    with os.fdopen(fd, "w") as f:
        json.dump(body, f)
    # Envoy runs as its own uid; a real build would match uids instead.
    os.chmod(tmp, 0o644)
    os.replace(tmp, directory / "secret.yaml")


def claude_token(login: Path) -> tuple[str, float]:
    oauth = json.loads(login.read_text())["claudeAiOauth"]
    return oauth["accessToken"], oauth["expiresAt"] / 1000


def codex_token(login: Path) -> tuple[str, float]:
    token = json.loads(login.read_text())["tokens"]["access_token"]
    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    return token, claims["exp"]


def follow(read, login: Path, directory: Path, watch: bool) -> None:
    token, expires = read(login)
    write(directory, f"Bearer {token}")
    print(f"secret written, token expires in {(expires - time.time()) / 60:.0f} min", flush=True)
    seen = login.stat().st_mtime
    while watch:
        time.sleep(2)
        mtime = login.stat().st_mtime
        if mtime != seen:
            seen = mtime
            token, expires = read(login)
            write(directory, f"Bearer {token}")
            print(f"rotated, expires in {(expires - time.time()) / 60:.0f} min", flush=True)


def main(argv: list[str]) -> None:
    mode = argv[0]
    if mode == "apikey":
        write(Path(argv[1]), os.environ["ANTHROPIC_API_KEY"])
    elif mode == "literal":
        write(Path(argv[2]), argv[1])
    elif mode in ("oauth", "codex"):
        read = claude_token if mode == "oauth" else codex_token
        follow(read, Path(argv[1]), Path(argv[2]), "--watch" in argv)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
