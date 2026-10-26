import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import TracebackType
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from adocker.execute import execute


class Process:
    def __init__(self, code: int = 0) -> None:
        self.wait = AsyncMock(return_value=code)
        self.kill = Mock()


class Pump:
    """A fake pump: its sink, its pipe's write end, and an `eof` that resolves unless held."""

    def __init__(self, sink: Callable[[bytes], object]) -> None:
        self.sink = sink
        self.write = PIPES[sink]
        self.eof: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        if sink not in HELD:
            self.eof.set_result(None)
        self.release: Mock = Mock()
        self.left = False
        MADE.append(self)

    async def __aenter__(self) -> "Pump":
        return self

    async def __aexit__(
        self,
        _type: type[BaseException] | None,
        _error: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        self.left = True


PIPES: dict[Callable[[bytes], object], int] = {}
HELD: set[Callable[[bytes], object]] = set()
MADE: list[Pump] = []


def out(_chunk: bytes) -> None: ...


def err(_chunk: bytes) -> None: ...


@pytest.fixture(autouse=True)
def pump_type() -> Iterator[None]:
    PIPES.clear()
    PIPES.update({out: 101, err: 102})
    HELD.clear()
    MADE.clear()
    with patch("adocker.execute.Pump", Pump):
        yield


@pytest.fixture
def process() -> Process:
    return Process()


@pytest.fixture
def exits() -> list[BaseException | None]:
    return []


@pytest.fixture(autouse=True)
def spawn(process: Process, exits: list[BaseException | None]) -> Iterator[Mock]:
    @asynccontextmanager
    async def spawned(*_args: object, **_options: object) -> AsyncIterator[Process]:
        try:
            yield process
        except BaseException as error:
            exits.append(error)
            raise
        exits.append(None)

    with patch("adocker.execute.spawn", side_effect=spawned) as m:
        yield m


async def run(*args: str, started: asyncio.Future[None] | None = None) -> int:
    return await execute(args, stdin=7, stdout=out, stderr=err, started=started)


def describe_execute() -> None:
    async def it_takes_its_streams_by_keyword_only() -> None:
        with pytest.raises(TypeError):
            await execute(("version",), 7, out, err)  # type: ignore[call-arg]

    async def it_returns_the_clients_exit_code(process: Process) -> None:
        process.wait.return_value = 3
        assert await run("rm", "x") == 3

    async def it_spawns_docker_on_its_stdin_writing_into_a_pump_per_sink(spawn: Mock) -> None:
        await run("version", "--format", "json")
        spawn.assert_called_once_with(
            "docker", "version", "--format", "json", stdin=7, stdout=101, stderr=102
        )
        assert [pump.sink for pump in MADE] == [out, err]

    async def it_releases_the_write_ends_before_waiting_on_docker(process: Process) -> None:
        async def released() -> int:
            assert all(pump.release.called for pump in MADE)
            return 0

        process.wait.side_effect = released
        await run("version")
        assert all(pump.release.call_args_list == [call()] for pump in MADE)

    async def it_leaves_the_pumps_when_done() -> None:
        await run("version")
        assert all(pump.left for pump in MADE)

    async def it_leaves_the_pumps_when_the_spawn_fails(spawn: Mock) -> None:
        spawn.side_effect = FileNotFoundError("docker")
        with pytest.raises(FileNotFoundError):
            await run("version")
        assert len(MADE) == 2
        assert all(pump.left for pump in MADE)

    async def it_signals_started_once_the_client_is_spawned(process: Process) -> None:
        started: asyncio.Future[None] = asyncio.get_running_loop().create_future()

        async def wait() -> int:
            assert started.done()
            return 0

        process.wait.side_effect = wait
        await run("run", started=started)
        assert started.result() is None

    async def it_leaves_started_alone_when_the_spawn_fails(spawn: Mock) -> None:
        started: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        spawn.side_effect = FileNotFoundError("docker")
        with pytest.raises(FileNotFoundError):
            await run("run", started=started)
        assert not started.done()

    async def it_returns_only_once_the_pumps_are_drained(process: Process) -> None:
        HELD.add(out)
        task = asyncio.create_task(run("build"))
        await asyncio.sleep(0.01)
        process.wait.assert_awaited_once_with()
        assert not task.done()
        MADE[0].eof.set_result(None)
        assert await task == 0

    async def it_raises_what_a_sink_raised_and_kills_the_client(process: Process) -> None:
        HELD.add(out)
        task = asyncio.create_task(run("build"))
        await asyncio.sleep(0.01)
        MADE[0].eof.set_exception(OSError("disk full"))
        with pytest.raises(OSError, match="disk full"):
            await task
        process.kill.assert_called_once_with()

    async def it_kills_and_waits_out_the_client_when_cancelled_while_it_runs(
        process: Process, exits: list[BaseException | None]
    ) -> None:
        running = asyncio.Event()

        async def wait() -> int:
            if not running.is_set():
                running.set()
                await asyncio.Event().wait()
            assert process.kill.called
            return -9

        process.wait.side_effect = wait
        task = asyncio.create_task(run("build"))
        await running.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        process.kill.assert_called_once_with()
        assert process.wait.await_count == 2
        assert [type(error) for error in exits] == [asyncio.CancelledError]

    async def it_kills_the_client_when_waiting_on_it_fails(process: Process) -> None:
        process.wait.side_effect = [OSError("wait failed"), -9]
        with pytest.raises(OSError, match="wait failed"):
            await run("build")
        process.kill.assert_called_once_with()

    async def it_tolerates_a_client_that_is_already_gone_when_killed(process: Process) -> None:
        process.kill.side_effect = ProcessLookupError
        HELD.add(out)
        task = asyncio.create_task(run("build"))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        process.kill.assert_called_once_with()

    async def it_leaves_the_pumps_eofs_alone_when_cancelled_while_draining(
        exits: list[BaseException | None],
    ) -> None:
        HELD.add(out)
        task = asyncio.create_task(run("build"))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not MADE[0].eof.done()
        assert [type(error) for error in exits] == [asyncio.CancelledError]

    async def it_leaves_the_client_alone_when_docker_finishes(process: Process) -> None:
        await run("version")
        process.kill.assert_not_called()

    async def it_leaves_the_block_cleanly_when_docker_finishes(
        exits: list[BaseException | None],
    ) -> None:
        await run("version")
        assert exits == [None]

    @pytest.mark.parametrize("file_stdout", [True, False])
    async def it_passes_files_through_and_pumps_only_the_sink(
        tmp_path: Path, spawn: Mock, file_stdout: bool
    ) -> None:
        with (tmp_path / "output").open("wb") as file:
            stdout, stderr = (file, err) if file_stdout else (out, file)
            assert await execute([], stdin=None, stdout=stdout, stderr=stderr) == 0
            spawn.assert_called_once_with(
                "docker",
                stdin=None,
                stdout=file if file_stdout else 101,
                stderr=102 if file_stdout else file,
            )
            assert len(MADE) == 1
            assert not file.closed
