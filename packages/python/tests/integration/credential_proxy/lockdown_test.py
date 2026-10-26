"""The credential sidecar starts within lockdown and shares its socket with an agent mount."""

from pathlib import Path
from uuid import uuid4

import pytest

from adocker import DockerException
from botbox.credential_proxy import Injection
from botbox.lockdown import CREDENTIAL_SOCKET_DIR, lockdown

INJECTION = Injection("api.anthropic.com", "/v1/messages", "Authorization")


async def test_lockdown_starts_the_credential_sidecar(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    token = uuid4().hex[:12]
    async with lockdown(
        (), tmp_path, token, output, injection=INJECTION, secret="Bearer fake-token"
    ) as jail:
        assert jail.credentials is not None
        assert jail.credentials.socket.is_socket()
        assert jail.credentials.container.name == f"botbox-credentials-{token}"
        assert jail.credential_mount is not None
        assert jail.credential_mount.source == str(jail.credentials.socket.parent)
        assert jail.credential_mount.target == CREDENTIAL_SOCKET_DIR
        assert jail.credential_mount.read_only
        assert (output / "credentials.log").is_file()
    with pytest.raises(DockerException):
        await jail.credentials.container.inspect()
