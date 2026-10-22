import asyncio
from collections.abc import Iterator
from types import TracebackType
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from botbox.docker.run_docker import LINGER, STDERR_LIMIT, run_docker

TIMEOUT = asyncio.timeout


class Process:
    def __init__(self, code: int = 0) -> None:
        self.code = code


class Captures:
    """Fake captures, the first filled with `stdout` and the second with `stderr`."""

    def __init__(self) -> None:
        self.made: list[Capture] = []
        self.output = [b'{"Version":"29"}\n', b""]
        self.eof = True

    def __call__(self, into: bytearray, limit: int | None = None) -> "Capture":
        capture = Capture(self, into, limit)
        self.made.append(capture)
        return capture


class Capture:
    def __init__(self, captures: Captures, into: bytearray, limit: int | None) -> None:
        self.captures = captures
        self.into = into
        self.limit = limit
        self.write = 100 + len(captures.made)
        self.eof: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.release = Mock()
        self.closed = False

    async def __aenter__(self) -> "Capture":
        self.into += self.captures.output[len(self.captures.made) - 1]
        if self.captures.eof:
            self.eof.set_result(None)
        return self

    async def __aexit__(
        self,
        _type: type[BaseException] | None,
        _error: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        self.closed = True
        if not self.eof.done():
            self.eof.set_result(None)


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


@pytest.fixture(autouse=True)
def captures() -> Iterator[Captures]:
    made = Captures()
    with patch("botbox.docker.run_docker.Capture", made):
        yield made


@pytest.fixture
async def process() -> Process:
    return Process()


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
    async def drained(_process: Process, eofs: tuple[asyncio.Future[None], ...]) -> None:
        await asyncio.gather(*eofs)

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
def lingering(captures: Captures, timeout: Mock) -> None:
    captures.eof = False
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

    async def it_captures_all_of_stdout_and_the_end_of_stderr(captures: Captures) -> None:
        await run_docker("version")
        assert [capture.limit for capture in captures.made] == [None, STDERR_LIMIT]

    async def it_spawns_docker_writing_to_its_captures(
        spawn: AsyncMock, captures: Captures
    ) -> None:
        await run_docker("version", "--format", "json")
        stdout, stderr = captures.made
        spawn.assert_awaited_once_with(
            ("version", "--format", "json"),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=stdout.write,
            stderr=stderr.write,
        )

    async def it_releases_the_write_ends_once_docker_has_them(captures: Captures) -> None:
        await run_docker("version")
        assert [capture.release.call_args_list for capture in captures.made] == [[call()]] * 2

    async def it_releases_and_closes_the_captures_when_the_spawn_fails(
        spawn: AsyncMock, captures: Captures, reap: AsyncMock
    ) -> None:
        spawn.side_effect = FileNotFoundError("docker")
        with pytest.raises(FileNotFoundError):
            await run_docker("version")
        assert all(capture.release.called and capture.closed for capture in captures.made)
        reap.assert_not_awaited()

    async def it_waits_for_the_client_to_exit(process: Process, exit_code: AsyncMock) -> None:
        await run_docker("version")
        exit_code.assert_awaited_once_with(process)

    async def it_then_gives_its_pipes_and_group_the_linger_to_finish(
        process: Process, ended: AsyncMock, captures: Captures, timeout: Mock
    ) -> None:
        await run_docker("version")
        ended.assert_awaited_once_with(process, tuple(c.eof for c in captures.made))
        timeout.assert_called_once_with(LINGER)

    async def it_leaves_alone_a_client_that_finished_cleanly(reap: AsyncMock) -> None:
        await run_docker("version")
        reap.assert_not_awaited()

    async def it_closes_the_captures_when_done(captures: Captures) -> None:
        await run_docker("version")
        assert all(capture.closed for capture in captures.made)

    @pytest.mark.usefixtures("lingering")
    async def it_reaps_a_group_that_outlives_the_linger(
        process: Process, reap: AsyncMock, captures: Captures
    ) -> None:
        assert await run_docker("version") == '{"Version":"29"}\n'
        reap.assert_awaited_once_with(process, *(c.eof for c in captures.made))

    @pytest.mark.usefixtures("lingering")
    async def it_raises_what_was_read_from_pipes_that_never_close(
        spawn: AsyncMock, captures: Captures
    ) -> None:
        spawn.return_value = Process(code=3)
        captures.output = [b"", b"said this\n"]
        with pytest.raises(DockerException) as raised:
            await run_docker("build")
        assert raised.value.stderr == "said this\n"
        assert all(capture.closed for capture in captures.made)

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

    async def it_raises_the_command_code_and_stderr_on_failure(
        spawn: AsyncMock, captures: Captures
    ) -> None:
        spawn.return_value = Process(code=1)
        captures.output = [b"", b"no such image\xff"]
        with pytest.raises(DockerException) as raised:
            await run_docker("rm", "x")
        assert raised.value.docker_command == ["docker", "rm", "x"]
        assert raised.value.return_code == 1
        assert raised.value.stderr == "no such image�"

    async def it_raises_when_a_signal_killed_the_client(spawn: AsyncMock) -> None:
        spawn.return_value = Process(code=-9)
        with pytest.raises(DockerException):
            await run_docker("rm", "x")

    async def it_decodes_stdout_leniently(captures: Captures) -> None:
        captures.output = [b"built\xff", b""]
        assert await run_docker("build") == "built�"

    async def it_reaps_the_client_when_cancelled_while_it_runs(
        process: Process, exit_code: AsyncMock, reap: AsyncMock, captures: Captures
    ) -> None:
        exit_code.side_effect = forever
        await cancelled(asyncio.create_task(run_docker("build")))
        reap.assert_awaited_once_with(process, *(c.eof for c in captures.made))
        assert all(capture.closed for capture in captures.made)

    async def it_reaps_the_group_when_cancelled_while_it_lingers(
        ended: AsyncMock, reap: AsyncMock
    ) -> None:
        ended.side_effect = forever
        await cancelled(asyncio.create_task(run_docker("build")))
        reap.assert_awaited_once()

    async def it_reaps_the_client_when_waiting_on_it_fails(
        exit_code: AsyncMock, reap: AsyncMock
    ) -> None:
        exit_code.side_effect = OSError("wait failed")
        with pytest.raises(OSError, match="wait failed"):
            await run_docker("build")
        reap.assert_awaited_once()
