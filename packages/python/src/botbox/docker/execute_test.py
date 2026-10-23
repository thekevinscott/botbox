import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from botbox.docker.execute import LINGER, execute

TIMEOUT = asyncio.timeout
TERM, KILL = 15, 9


class Process:
    def __init__(self, code: int = 0) -> None:
        self.code = code


class Capture:
    """A fake capture: its pipe's write end and an `eof` that resolves unless held `open`."""

    def __init__(self, fd: int, *, open: bool = False) -> None:
        self.write = fd
        self.eof: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        if not open:
            self.eof.set_result(None)
        self.release = Mock()
        self.unblock = Mock()


async def forever(*_args: object) -> None:
    await asyncio.Event().wait()


@pytest.fixture
async def captures() -> tuple[Capture, Capture]:
    return Capture(101), Capture(102)


@pytest.fixture
async def process() -> Process:
    return Process()


@pytest.fixture(autouse=True)
def spawn(process: Process) -> Iterator[AsyncMock]:
    with patch("botbox.docker.execute.spawn", autospec=True, return_value=process) as m:
        yield m


@pytest.fixture(autouse=True)
def exit_code() -> Iterator[AsyncMock]:
    async def code(process: Process) -> int:
        return process.code

    with patch("botbox.docker.execute.exit_code", autospec=True, side_effect=code) as m:
        yield m


@pytest.fixture(autouse=True)
def ended() -> Iterator[AsyncMock]:
    async def drained(_process: Process, eofs: tuple[asyncio.Future[None], ...]) -> None:
        await asyncio.gather(*eofs)

    with patch("botbox.docker.execute.ended", autospec=True, side_effect=drained) as m:
        yield m


@pytest.fixture(autouse=True)
def reap() -> Iterator[AsyncMock]:
    with patch("botbox.docker.execute.reap", autospec=True) as m:
        yield m


@pytest.fixture
def timeout() -> Iterator[Mock]:
    with patch("botbox.docker.execute.asyncio.timeout", side_effect=asyncio.timeout) as m:
        yield m


@pytest.fixture
async def lingering(timeout: Mock) -> tuple[Capture, Capture]:
    timeout.side_effect = lambda _delay: TIMEOUT(0.01)
    return Capture(101, open=True), Capture(102, open=True)


async def run(captures: tuple[Capture, Capture], *args: str, **options: int) -> int:
    stdout, stderr = captures
    return await execute(args, stdin=7, stdout=stdout, stderr=stderr, **options)  # type: ignore[arg-type]


async def cancelled(task: asyncio.Task[int]) -> None:
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def describe_execute() -> None:
    def it_lets_the_clients_descendants_outlive_it_by_two_seconds() -> None:
        assert LINGER == 2

    async def it_takes_its_streams_by_keyword_only(captures: tuple[Capture, Capture]) -> None:
        with pytest.raises(TypeError):
            await execute(("version",), 7, *captures)  # type: ignore[call-arg, arg-type]

    async def it_returns_the_clients_exit_code(
        spawn: AsyncMock, captures: tuple[Capture, Capture]
    ) -> None:
        spawn.return_value = Process(code=3)
        assert await run(captures, "rm", "x") == 3

    async def it_spawns_docker_on_its_stdin_writing_to_its_captures(
        spawn: AsyncMock, captures: tuple[Capture, Capture]
    ) -> None:
        await run(captures, "version", "--format", "json")
        spawn.assert_awaited_once_with(
            ("version", "--format", "json"), stdin=7, stdout=101, stderr=102
        )

    async def it_releases_the_write_ends_once_docker_has_them(
        captures: tuple[Capture, Capture],
    ) -> None:
        await run(captures, "version")
        assert [capture.release.call_args_list for capture in captures] == [[call()]] * 2

    async def it_stops_pausing_the_captures_once_the_client_exits(
        exit_code: AsyncMock, captures: tuple[Capture, Capture]
    ) -> None:
        async def code(_process: Process) -> int:
            assert not any(capture.unblock.called for capture in captures)
            return 0

        exit_code.side_effect = code
        await run(captures, "version")
        assert [capture.unblock.call_args_list for capture in captures] == [[call()]] * 2

    async def it_stops_pausing_the_captures_before_reaping_a_failed_wait(
        exit_code: AsyncMock, reap: AsyncMock, captures: tuple[Capture, Capture]
    ) -> None:
        exit_code.side_effect = OSError("wait failed")
        unblocked: list[bool] = []
        reap.side_effect = lambda *_a, **_k: unblocked.extend(c.unblock.called for c in captures)
        with pytest.raises(OSError, match="wait failed"):
            await run(captures, "build")
        assert unblocked == [True, True]

    async def it_releases_the_captures_when_the_spawn_fails(
        spawn: AsyncMock, captures: tuple[Capture, Capture], reap: AsyncMock
    ) -> None:
        spawn.side_effect = FileNotFoundError("docker")
        with pytest.raises(FileNotFoundError):
            await run(captures, "version")
        assert all(capture.release.called for capture in captures)
        reap.assert_not_awaited()

    async def it_waits_for_the_client_to_exit(
        process: Process, exit_code: AsyncMock, captures: tuple[Capture, Capture]
    ) -> None:
        await run(captures, "version")
        exit_code.assert_awaited_once_with(process)

    async def it_then_gives_its_pipes_and_group_the_linger_to_finish(
        process: Process, ended: AsyncMock, captures: tuple[Capture, Capture], timeout: Mock
    ) -> None:
        await run(captures, "version")
        ended.assert_awaited_once_with(process, tuple(c.eof for c in captures))
        timeout.assert_called_once_with(LINGER)

    async def it_leaves_alone_a_client_that_finished_cleanly(
        reap: AsyncMock, captures: tuple[Capture, Capture]
    ) -> None:
        await run(captures, "version")
        reap.assert_not_awaited()

    async def it_reaps_a_group_that_outlives_the_linger(
        process: Process, reap: AsyncMock, lingering: tuple[Capture, Capture]
    ) -> None:
        assert await run(lingering, "version") == 0
        reap.assert_awaited_once_with(process, *(c.eof for c in lingering), signum=TERM)

    async def it_returns_the_code_of_a_client_whose_pipes_never_close(
        spawn: AsyncMock, lingering: tuple[Capture, Capture]
    ) -> None:
        spawn.return_value = Process(code=3)
        assert await run(lingering, "build") == 3

    async def it_keeps_a_cancel_that_lands_while_it_reaps(
        reap: AsyncMock, lingering: tuple[Capture, Capture]
    ) -> None:
        finished = asyncio.Event()

        async def slow(*_args: object, **_options: object) -> None:
            await asyncio.sleep(0.05)
            finished.set()

        reap.side_effect = slow
        task = asyncio.create_task(run(lingering, "build"))
        await asyncio.sleep(0.03)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()

    async def it_reaps_the_client_when_cancelled_while_it_runs(
        process: Process,
        exit_code: AsyncMock,
        reap: AsyncMock,
        captures: tuple[Capture, Capture],
    ) -> None:
        exit_code.side_effect = forever
        await cancelled(asyncio.create_task(run(captures, "build")))
        reap.assert_awaited_once_with(process, *(c.eof for c in captures), signum=TERM)

    async def it_reaps_starting_with_the_signal_it_is_given(
        process: Process,
        exit_code: AsyncMock,
        reap: AsyncMock,
        captures: tuple[Capture, Capture],
    ) -> None:
        exit_code.side_effect = forever
        await cancelled(asyncio.create_task(run(captures, "run", signum=KILL)))
        reap.assert_awaited_once_with(process, *(c.eof for c in captures), signum=KILL)

    async def it_reaps_the_group_when_cancelled_while_it_lingers(
        ended: AsyncMock, reap: AsyncMock, captures: tuple[Capture, Capture]
    ) -> None:
        ended.side_effect = forever
        await cancelled(asyncio.create_task(run(captures, "build")))
        reap.assert_awaited_once()

    async def it_reaps_the_client_when_waiting_on_it_fails(
        exit_code: AsyncMock, reap: AsyncMock, captures: tuple[Capture, Capture]
    ) -> None:
        exit_code.side_effect = OSError("wait failed")
        with pytest.raises(OSError, match="wait failed"):
            await run(captures, "build")
        reap.assert_awaited_once()
