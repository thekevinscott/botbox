"""The credential sidecar starts within lockdown and serves its socket in the run's volume."""

from pathlib import Path
from uuid import uuid4

import pytest

from adocker import DockerException
from botbox.credential_proxy import Credential, Injection
from botbox.lockdown import CREDENTIALS_ENV, lockdown

CREDENTIAL = Credential(
    Injection("api.anthropic.com", "/v1/messages", "Authorization"), "Bearer fake-token"
)


async def test_lockdown_starts_the_credential_sidecar(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    token = uuid4().hex[:12]
    async with lockdown((), tmp_path, token, output, credential=CREDENTIAL) as jail:
        assert jail.credentials is not None
        assert jail.credentials.socket == "/run/botbox/credentials.sock"
        assert jail.credentials.container.name == f"botbox-credentials-{token}"
        assert jail.envs[CREDENTIALS_ENV] == "1"
        await jail.proxy.exec(
            "socat", "-u", "OPEN:/dev/null", f"UNIX-CONNECT:{jail.credentials.socket}"
        )
        assert (output / "credentials.log").is_file()
    with pytest.raises(DockerException):
        await jail.credentials.container.inspect()
