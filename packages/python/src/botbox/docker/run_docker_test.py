import asyncio
from collections.abc import Iterator
from types import TracebackType
from unittest.mock import AsyncMock, patch

import pytest

from botbox.docker.run_docker import STDERR_LIMIT, run_docker


class Capture:
    """A fake capture that records its limit and whether it was left."""

    def __init__(self, into: bytearray, limit: int | None = None) -> None:
        self.into = into
        self.limit = limit
        self.closed = False
        MADE.append(self)

    async def __aenter__(self) -> "Capture":
        return self

    async def __aexit__(
        self,
        _type: type[BaseException] | None,
        _error: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        self.closed = True


MADE: list[Capture] = []


class DockerException(Exception):
    def __init__(self, docker_command: list[str], return_code: int, stderr: str) -> None:
        self.docker_command = docker_command
        self.return_code = return_code
        self.stderr = stderr


@pytest.fixture(autouse=True)
def docker_exception() -> Iterator[None]:
    with patch("botbox.docker.run_docker.DockerException", DockerException):
        yield


@pytest.fixture(autouse=True)
def captures() -> Iterator[list[Capture]]:
    MADE.clear()
    with patch("botbox.docker.run_docker.Capture", Capture):
        yield MADE


@pytest.fixture
def output() -> list[bytes]:
    """What the client writes to its stdout and stderr."""
    return [b'{"Version":"29"}\n', b""]


@pytest.fixture(autouse=True)
def execute(output: list[bytes]) -> Iterator[AsyncMock]:
    async def write(_args: object, *, stdout: Capture, stderr: Capture, **_options: object) -> int:
        stdout.into += output[0]
        stderr.into += output[1]
        return 0

    with patch("botbox.docker.run_docker.execute", autospec=True, side_effect=write) as m:
        yield m


def describe_run_docker() -> None:
    def it_keeps_64k_of_stderr() -> None:
        assert STDERR_LIMIT == 64 * 1024

    async def it_returns_stdout() -> None:
        assert await run_docker("version") == '{"Version":"29"}\n'

    async def it_captures_all_of_stdout_and_the_end_of_stderr(captures: list[Capture]) -> None:
        await run_docker("version")
        assert [capture.limit for capture in captures] == [None, STDERR_LIMIT]

    async def it_runs_docker_with_no_stdin_writing_to_its_captures(
        execute: AsyncMock, captures: list[Capture]
    ) -> None:
        await run_docker("version", "--format", "json")
        stdout, stderr = captures
        execute.assert_awaited_once_with(
            ("version", "--format", "json"),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
        )

    async def it_closes_the_captures_when_done(captures: list[Capture]) -> None:
        await run_docker("version")
        assert all(capture.closed for capture in captures)

    async def it_closes_the_captures_when_it_fails(
        execute: AsyncMock, captures: list[Capture]
    ) -> None:
        execute.side_effect = OSError("wait failed")
        with pytest.raises(OSError, match="wait failed"):
            await run_docker("version")
        assert all(capture.closed for capture in captures)

    async def it_raises_the_command_code_and_stderr_on_failure(
        execute: AsyncMock, output: list[bytes]
    ) -> None:
        output[:] = [b"", b"no such image\xff"]
        side_effect = execute.side_effect

        async def failing(*args: object, **options: object) -> int:
            await side_effect(*args, **options)
            return 1

        execute.side_effect = failing
        with pytest.raises(DockerException) as raised:
            await run_docker("rm", "x")
        assert raised.value.docker_command == ["docker", "rm", "x"]
        assert raised.value.return_code == 1
        assert raised.value.stderr == "no such image�"

    async def it_raises_when_a_signal_killed_the_client(execute: AsyncMock) -> None:
        execute.side_effect = None
        execute.return_value = -9
        with pytest.raises(DockerException):
            await run_docker("rm", "x")

    async def it_decodes_stdout_leniently(output: list[bytes]) -> None:
        output[:] = [b"built\xff", b""]
        assert await run_docker("build") == "built�"
