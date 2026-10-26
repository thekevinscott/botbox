import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from botbox.credential_proxy.CredentialProxy import ROTATE, CredentialProxy
from botbox.credential_proxy.envoy_config import SECRET_FILE


class Execute:
    def __init__(self) -> None:
        self.args: list[str] = []
        self.stdin = b""
        self.stdin_fd = -1
        self.code = 0
        self.stderr = b""

    async def __call__(self, args: list[str], **options: Any) -> int:
        self.args = args
        self.stdin_fd = options["stdin"]
        self.stdin = os.read(options["stdin"], 1 << 16)
        os.write(options["stderr"].write, self.stderr)
        options["stderr"].release()
        await options["stderr"].eof
        return self.code


@pytest.fixture(autouse=True)
def execute() -> Iterator[Execute]:
    fake = Execute()
    with patch(f"{__package__}.CredentialProxy.execute", fake):
        yield fake


def describe_CredentialProxy() -> None:
    def it_holds_its_name_and_socket() -> None:
        proxy = CredentialProxy("botbox-credentials-1", Path("/s/c.sock"))
        assert proxy.name == "botbox-credentials-1"
        assert proxy.socket == Path("/s/c.sock")

    def describe_rotate() -> None:
        async def it_renames_the_new_secret_over_the_file(execute: Execute) -> None:
            await CredentialProxy("p", Path("/s")).rotate("Bearer two")
            assert execute.args == [
                "exec",
                "--interactive",
                "p",
                "sh",
                "-c",
                ROTATE,
                "sh",
                SECRET_FILE,
            ]
            assert 'mv "$1.next" "$1"' in ROTATE
            (resource,) = json.loads(execute.stdin)["resources"]
            assert resource["generic_secret"]["secret"]["inline_string"] == "Bearer two"

        async def it_closes_the_pipe(execute: Execute) -> None:
            await CredentialProxy("p", Path("/s")).rotate("v")
            with pytest.raises(OSError):
                os.fstat(execute.stdin_fd)

        async def it_raises_with_what_docker_said(execute: Execute) -> None:
            execute.code, execute.stderr = 1, b"No such container: p"
            with pytest.raises(Exception, match="No such container: p") as error:
                await CredentialProxy("p", Path("/s")).rotate("v")
            assert error.value.return_code == 1  # type: ignore[attr-defined]
            assert error.value.docker_command[:3] == ["docker", "exec", "--interactive"]  # type: ignore[attr-defined]
