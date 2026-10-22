import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock, patch

import pytest

from botbox.docker.run_docker import LINGER, STDERR_LIMIT, run_docker

TIMEOUT = asyncio.timeout


def stream(data: bytes, *, eof: bool = True) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    if eof:
        reader.feed_eof()
    return reader


class Process:
    def __init__(
        self, stdout: bytes = b"", stderr: bytes = b"", code: int = 0, *, eof: bool = True
    ) -> None:
        self.stdout = stream(stdout, eof=eof)
        self.stderr = stream(stderr, eof=eof)
        self.code = code
        self._transport = Mock()


class DockerException(Exception):
    def __init__(self, docker_command: list[str], return_code: int, stderr: str) -> None:
        self.docker_command = docker_command
        self.return_code = return_code
        self.stderr = stderr


async def forever(*_args: object) -> None:
    await asyncio.Event().wait()


@pytest.fixture(autouse=True)
def docker_exception() -> Iterator[None]:
    with patch("botbox.docker.run_docker.DockerException", DockerException):
        yield


@pytest.fixture
async def process() -> Process:
    return Process(stdout=b'{"Version":"29"}\n')


@pytest.fixture(autouse=True)
def spawn(process: Process) -> Iterator[AsyncMock]:
    with patch("botbox.docker.run_docker.spawn", autospec=True, return_value=process) as m:
        yield m


@pytest.fixture(autouse=True)
def exit_code() -> Iterator[AsyncMock]:
    async def code(process: Process) -> int:
        return process.code

    with patch("botbox.docker.run_docker.exit_code", autospec=True, side_effect=code) as m:
        yield m


@pytest.fixture(autouse=True)
def ended() -> Iterator[AsyncMock]:
    async def drained(_process: Process, drains: tuple[asyncio.Future[None], ...]) -> None:
        await asyncio.gather(*drains)

    with patch("botbox.docker.run_docker.ended", autospec=True, side_effect=drained) as m:
        yield m


@pytest.fixture(autouse=True)
def reap() -> Iterator[AsyncMock]:
    with patch("botbox.docker.run_docker.reap", autospec=True) as m:
        yield m


@pytest.fixture
def timeout() -> Iterator[Mock]:
    with patch("botbox.docker.run_docker.asyncio.timeout", side_effect=asyncio.timeout) as m:
        yield m


@pytest.fixture
def lingering(ended: AsyncMock, timeout: Mock) -> None:
    ended.side_effect = forever
    timeout.side_effect = lambda _delay: TIMEOUT(0.01)


async def cancelled(task: asyncio.Task[str]) -> None:
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def describe_run_docker() -> None:
    def it_keeps_64k_of_stderr() -> None:
        assert STDERR_LIMIT == 64 * 1024

    def it_lets_the_clients_descendants_outlive_it_by_two_seconds() -> None:
        assert LINGER == 2

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

    async def it_waits_for_the_client_to_exit(process: Process, exit_code: AsyncMock) -> None:
        await run_docker("version")
        exit_code.assert_awaited_once_with(process)

    async def it_then_gives_its_pipes_and_group_the_linger_to_finish(
        process: Process, ended: AsyncMock, timeout: Mock
    ) -> None:
        await run_docker("version")
        reaped, drains = ended.await_args_list[0].args
        assert reaped is process
        assert len(drains) == 2
        timeout.assert_called_once_with(LINGER)

    async def it_leaves_alone_a_client_that_finished_cleanly(reap: AsyncMock) -> None:
        await run_docker("version")
        reap.assert_not_awaited()

    async def it_closes_the_pipes_when_done(process: Process) -> None:
        await run_docker("version")
        process._transport.close.assert_called_once_with()

    @pytest.mark.usefixtures("lingering")
    async def it_reaps_a_group_that_outlives_the_linger(process: Process, reap: AsyncMock) -> None:
        assert await run_docker("version") == '{"Version":"29"}\n'
        reaped, *drains = reap.await_args_list[0].args
        assert reaped is process
        assert len(drains) == 2

    @pytest.mark.usefixtures("lingering")
    async def it_returns_what_was_read_from_pipes_that_never_close(spawn: AsyncMock) -> None:
        spawn.return_value = Process(stdout=b"built\n", eof=False)
        assert await run_docker("build") == "built\n"

    @pytest.mark.usefixtures("lingering")
    async def it_raises_what_was_read_from_pipes_that_never_close(spawn: AsyncMock) -> None:
        spawn.return_value = Process(stderr=b"said this\n", code=3, eof=False)
        with pytest.raises(DockerException) as raised:
            await run_docker("build")
        assert raised.value.stderr == "said this\n"

    @pytest.mark.usefixtures("lingering")
    async def it_stops_the_readers_of_pipes_that_never_close(
        spawn: AsyncMock, reap: AsyncMock
    ) -> None:
        process = Process(eof=False)
        spawn.return_value = process
        await run_docker("build")
        _, *drains = reap.await_args_list[0].args
        assert all(drain.cancelled() for drain in drains)
        process._transport.close.assert_called_once_with()

    @pytest.mark.usefixtures("lingering")
    async def it_keeps_a_cancel_that_lands_while_it_reaps(reap: AsyncMock) -> None:
        finished = asyncio.Event()

        async def slow(*_args: object) -> None:
            await asyncio.sleep(0.05)
            finished.set()

        reap.side_effect = slow
        task = asyncio.create_task(run_docker("build"))
        await asyncio.sleep(0.03)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()

    async def it_raises_the_command_code_and_stderr_on_failure(spawn: AsyncMock) -> None:
        spawn.return_value = Process(stderr=b"no such image\xff", code=1)
        with pytest.raises(DockerException) as raised:
            await run_docker("rm", "x")
        assert raised.value.docker_command == ["docker", "rm", "x"]
        assert raised.value.return_code == 1
        assert raised.value.stderr == "no such image�"

    async def it_raises_when_a_signal_killed_the_client(spawn: AsyncMock) -> None:
        spawn.return_value = Process(code=-9)
        with pytest.raises(DockerException):
            await run_docker("rm", "x")

    async def it_keeps_only_the_end_of_a_long_stderr(spawn: AsyncMock) -> None:
        spawn.return_value = Process(stderr=b"x" * STDERR_LIMIT * 2 + b"the error", code=1)
        with pytest.raises(DockerException) as raised:
            await run_docker("build")
        assert raised.value.stderr.endswith("the error")
        assert len(raised.value.stderr) == STDERR_LIMIT

    async def it_reaps_the_client_when_cancelled_while_it_runs(
        process: Process, exit_code: AsyncMock, reap: AsyncMock
    ) -> None:
        exit_code.side_effect = forever
        await cancelled(asyncio.create_task(run_docker("build")))
        reaped, *drains = reap.await_args_list[0].args
        assert reaped is process
        assert len(drains) == 2
        process._transport.close.assert_called_once_with()

    async def it_reaps_the_group_when_cancelled_while_it_lingers(
        ended: AsyncMock, reap: AsyncMock
    ) -> None:
        ended.side_effect = forever
        await cancelled(asyncio.create_task(run_docker("build")))
        reap.assert_awaited_once()

    async def it_reaps_the_client_when_waiting_on_it_fails(
        exit_code: AsyncMock, reap: AsyncMock
    ) -> None:
        exit_code.side_effect = OSError("pidfd")
        with pytest.raises(OSError, match="pidfd"):
            await run_docker("build")
        reap.assert_awaited_once()
