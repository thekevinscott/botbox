import asyncio
from collections.abc import Iterator
from typing import IO
from unittest.mock import AsyncMock, patch

import pytest

from adocker.utils.run_docker import STDERR_LIMIT, run_docker


class DockerException(Exception):
    def __init__(self, docker_command: list[str], return_code: int, stderr: str) -> None:
        self.docker_command = docker_command
        self.return_code = return_code
        self.stderr = stderr


@pytest.fixture(autouse=True)
def docker_exception() -> Iterator[None]:
    with patch("adocker.utils.run_docker.DockerException", DockerException):
        yield


@pytest.fixture
def output() -> list[bytes]:
    """What the client writes to its stdout and stderr, and the code it exits with."""
    return [b'{"Version":"29"}\n', b""]


@pytest.fixture
def code() -> list[int]:
    return [0]


@pytest.fixture
def files() -> list[IO[bytes]]:
    return []


@pytest.fixture(autouse=True)
def execute(output: list[bytes], code: list[int], files: list[IO[bytes]]) -> Iterator[AsyncMock]:
    async def write(
        _args: object, *, stdout: IO[bytes], stderr: IO[bytes], **_options: object
    ) -> int:
        files.extend([stdout, stderr])
        stdout.write(output[0])
        stderr.write(output[1])
        return code[0]

    with patch("adocker.utils.run_docker.execute", autospec=True, side_effect=write) as m:
        yield m


def describe_run_docker() -> None:
    def it_keeps_64k_of_stderr() -> None:
        assert STDERR_LIMIT == 64 * 1024

    async def it_returns_stdout() -> None:
        assert await run_docker("version") == '{"Version":"29"}\n'

    async def it_runs_docker_with_no_stdin_by_default(execute: AsyncMock) -> None:
        await run_docker("version", "--format", "json")
        [(args, options)] = [(c.args, c.kwargs) for c in execute.await_args_list]
        assert args == (("version", "--format", "json"),)
        assert options["stdin"] == asyncio.subprocess.DEVNULL

    async def it_passes_its_stdin_on(execute: AsyncMock) -> None:
        await run_docker("exec", stdin=9)
        assert execute.await_args_list[0].kwargs["stdin"] == 9

    async def it_writes_to_temp_files_and_closes_them(files: list[IO[bytes]]) -> None:
        await run_docker("version")
        assert len(files) == 2
        assert files[0] is not files[1]
        assert all(file.closed for file in files)

    async def it_closes_the_files_when_it_fails(execute: AsyncMock, files: list[IO[bytes]]) -> None:
        side_effect = execute.side_effect

        async def failing(*args: object, **options: object) -> int:
            await side_effect(*args, **options)
            raise OSError("wait failed")

        execute.side_effect = failing
        with pytest.raises(OSError, match="wait failed"):
            await run_docker("version")
        assert all(file.closed for file in files)

    async def it_raises_the_command_code_and_stderr_on_failure(
        output: list[bytes], code: list[int]
    ) -> None:
        output[:] = [b"", b"no such image\xff"]
        code[0] = 1
        with pytest.raises(DockerException) as raised:
            await run_docker("rm", "x")
        assert raised.value.docker_command == ["docker", "rm", "x"]
        assert raised.value.return_code == 1
        assert raised.value.stderr == "no such image\N{REPLACEMENT CHARACTER}"

    async def it_raises_with_only_the_end_of_a_long_stderr(
        output: list[bytes], code: list[int]
    ) -> None:
        output[:] = [b"", b"aaa" + b"b" * STDERR_LIMIT]
        code[0] = 1
        with pytest.raises(DockerException) as raised:
            await run_docker("rm", "x")
        assert raised.value.stderr == "b" * STDERR_LIMIT

    async def it_raises_when_a_signal_killed_the_client(code: list[int]) -> None:
        code[0] = -9
        with pytest.raises(DockerException):
            await run_docker("rm", "x")

    async def it_decodes_stdout_leniently(output: list[bytes]) -> None:
        output[:] = [b"built\xff", b""]
        assert await run_docker("build") == "built\N{REPLACEMENT CHARACTER}"
