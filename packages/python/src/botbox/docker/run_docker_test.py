import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from botbox.docker.DockerException import DockerException
from botbox.docker.run_docker import STDERR_LIMIT, run_docker


def stream(data: bytes, *, eof: bool = True) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    if eof:
        reader.feed_eof()
    return reader


class Process:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", code: int = 0) -> None:
        self.stdout = stream(stdout)
        self.stderr = stream(stderr)
        self.code = code
        self.exited = asyncio.Event()
        self.exited.set()

    async def wait(self) -> int:
        await self.exited.wait()
        return self.code


@pytest.fixture
def process() -> Process:
    return Process(stdout=b'{"Version":"29"}\n')


@pytest.fixture(autouse=True)
def spawn(process: Process) -> Iterator[AsyncMock]:
    with patch("botbox.docker.run_docker.spawn", autospec=True, return_value=process) as m:
        yield m


@pytest.fixture(autouse=True)
def reap() -> Iterator[AsyncMock]:
    with patch("botbox.docker.run_docker.reap", autospec=True) as m:
        yield m


def describe_run_docker() -> None:
    def it_keeps_64k_of_stderr() -> None:
        assert STDERR_LIMIT == 64 * 1024

    async def it_returns_stdout() -> None:
        assert await run_docker("version") == '{"Version":"29"}\n'

    async def it_spawns_docker_with_no_stdin_and_both_outputs_piped(spawn: AsyncMock) -> None:
        await run_docker("version", "--format", "json")
        spawn.assert_awaited_once_with(
            ("version", "--format", "json"),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def it_raises_the_command_code_and_stderr_on_failure(spawn: AsyncMock) -> None:
        spawn.return_value = Process(stderr=b"no such image\xff", code=1)
        with pytest.raises(DockerException) as raised:
            await run_docker("rm", "x")
        assert raised.value.docker_command == ["docker", "rm", "x"]
        assert raised.value.return_code == 1
        assert raised.value.stderr == "no such image�"

    async def it_keeps_only_the_end_of_a_long_stderr(spawn: AsyncMock) -> None:
        spawn.return_value = Process(stderr=b"x" * STDERR_LIMIT * 2 + b"the error", code=1)
        with pytest.raises(DockerException) as raised:
            await run_docker("build")
        assert raised.value.stderr.endswith("the error")
        assert len(raised.value.stderr) == STDERR_LIMIT

    async def it_reaps_the_process_and_its_drains_when_cancelled(
        spawn: AsyncMock, reap: AsyncMock
    ) -> None:
        process = Process()
        process.exited.clear()
        spawn.return_value = process
        task = asyncio.create_task(run_docker("build"))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        (reaped, *drains), _ = reap.await_args
        assert reaped is process
        assert len(drains) == 2

    async def it_keeps_reaping_through_a_second_cancel(spawn: AsyncMock, reap: AsyncMock) -> None:
        process = Process()
        process.exited.clear()
        spawn.return_value = process
        reaped = asyncio.Event()

        async def slow_reap(*_args: object) -> None:
            await asyncio.sleep(0.05)
            reaped.set()

        reap.side_effect = slow_reap
        task = asyncio.create_task(run_docker("build"))
        await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert reaped.is_set()

    async def it_reaps_when_reading_fails(spawn: AsyncMock, reap: AsyncMock) -> None:
        process = Process()

        async def broken() -> int:
            raise OSError("broken pipe")

        process.wait = broken  # type: ignore[method-assign]
        spawn.return_value = process
        with pytest.raises(OSError, match="broken pipe"):
            await run_docker("build")
        reap.assert_awaited_once()

    async def it_does_not_reap_a_process_that_exited(reap: AsyncMock) -> None:
        await run_docker("version")
        reap.assert_not_awaited()
