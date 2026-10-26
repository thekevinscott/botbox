import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

from botbox.credential_proxy.CredentialProxy import ROTATE, CredentialProxy


class Exec:
    def __init__(self) -> None:
        self.command: tuple[str, ...] = ()
        self.stdin = b""
        self.stdin_fd = -1
        self.raises: Exception | None = None

    async def __call__(self, *command: str, **options: Any) -> str:
        self.command = command
        self.stdin_fd = options["stdin"]
        self.stdin = os.read(options["stdin"], 1 << 16)
        if self.raises is not None:
            raise self.raises
        return ""


@pytest.fixture(autouse=True)
def collaborators() -> Iterator[None]:
    with (
        patch(f"{__package__}.CredentialProxy.SECRET_FILE", "/secrets/s.json"),
        patch(f"{__package__}.CredentialProxy.sds_secret", lambda value: f"sds {value}".encode()),
    ):
        yield


@pytest.fixture
def container() -> Mock:
    return Mock(exec=Exec())


def describe_CredentialProxy() -> None:
    def it_holds_its_container_and_socket(container: Mock) -> None:
        proxy = CredentialProxy(container, Path("/s/c.sock"))
        assert proxy.container is container
        assert proxy.socket == Path("/s/c.sock")

    def describe_rotate() -> None:
        async def it_renames_the_new_secret_over_the_file_in_its_container(
            container: Mock,
        ) -> None:
            await CredentialProxy(container, Path("/s")).rotate("Bearer two")
            execute = container.exec
            assert execute.command == ("sh", "-c", ROTATE, "sh", "/secrets/s.json")
            assert ROTATE == 'cat >"$1.next" && mv "$1.next" "$1"'
            assert execute.stdin == b"sds Bearer two"

        async def it_closes_the_pipe(container: Mock) -> None:
            await CredentialProxy(container, Path("/s")).rotate("v")
            with pytest.raises(OSError):
                os.fstat(container.exec.stdin_fd)

        async def it_raises_what_docker_raised_and_closes_the_pipe(container: Mock) -> None:
            execute = container.exec
            execute.raises = RuntimeError("No such container: p")
            with pytest.raises(RuntimeError, match="No such container: p"):
                await CredentialProxy(container, Path("/s")).rotate("v")
            with pytest.raises(OSError):
                os.fstat(execute.stdin_fd)
