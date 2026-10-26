import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from adocker.execute import execute


class Process:
    def __init__(self, code: int = 0) -> None:
        self.wait = AsyncMock(return_value=code)


class Capture:
    """A fake capture: its pipe's write end and an `eof` that resolves unless held `open`."""

    def __init__(self, fd: int, *, open: bool = False) -> None:
        self.write = fd
        self.eof: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        if not open:
            self.eof.set_result(None)
        self.release: Mock = Mock()


@pytest.fixture(autouse=True)
def capture_type() -> Iterator[None]:
    with patch("adocker.execute.Capture", Capture):
        yield


@pytest.fixture
async def captures() -> tuple[Capture, Capture]:
    return Capture(101), Capture(102)


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


async def run(captures: tuple[Capture, Capture], *args: str) -> int:
    stdout, stderr = captures
    return await execute(args, stdin=7, stdout=stdout, stderr=stderr)  # type: ignore[arg-type]


def describe_execute() -> None:
    async def it_takes_its_streams_by_keyword_only(captures: tuple[Capture, Capture]) -> None:
        with pytest.raises(TypeError):
            await execute(("version",), 7, *captures)  # type: ignore[call-arg, arg-type]

    async def it_returns_the_clients_exit_code(
        process: Process, captures: tuple[Capture, Capture]
    ) -> None:
        process.wait.return_value = 3
        assert await run(captures, "rm", "x") == 3

    async def it_spawns_docker_on_its_stdin_writing_to_its_captures(
        spawn: Mock, captures: tuple[Capture, Capture]
    ) -> None:
        await run(captures, "version", "--format", "json")
        spawn.assert_called_once_with(
            "docker", "version", "--format", "json", stdin=7, stdout=101, stderr=102
        )

    async def it_releases_the_write_ends_before_waiting_on_docker(
        process: Process, captures: tuple[Capture, Capture]
    ) -> None:
        async def released() -> int:
            assert all(capture.release.called for capture in captures)
            return 0

        process.wait.side_effect = released
        await run(captures, "version")
        assert all(call() in capture.release.call_args_list for capture in captures)

    async def it_releases_the_captures_when_the_spawn_fails(
        spawn: Mock, captures: tuple[Capture, Capture]
    ) -> None:
        spawn.side_effect = FileNotFoundError("docker")
        with pytest.raises(FileNotFoundError):
            await run(captures, "version")
        assert all(capture.release.called for capture in captures)

    async def it_returns_only_once_the_captures_are_drained(process: Process) -> None:
        held = Capture(101, open=True), Capture(102)
        task = asyncio.create_task(run(held, "build"))
        await asyncio.sleep(0.01)
        process.wait.assert_awaited_once_with()
        assert not task.done()
        held[0].eof.set_result(None)
        assert await task == 0

    async def it_stops_the_client_when_cancelled_while_it_runs(
        process: Process, captures: tuple[Capture, Capture], exits: list[BaseException | None]
    ) -> None:
        process.wait.side_effect = asyncio.Event().wait
        task = asyncio.create_task(run(captures, "build"))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert [type(error) for error in exits] == [asyncio.CancelledError]

    async def it_leaves_the_captures_eofs_alone_when_cancelled_while_draining(
        exits: list[BaseException | None],
    ) -> None:
        held = Capture(101, open=True), Capture(102)
        task = asyncio.create_task(run(held, "build"))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not held[0].eof.done()
        assert [type(error) for error in exits] == [asyncio.CancelledError]

    async def it_leaves_the_block_cleanly_when_docker_finishes(
        captures: tuple[Capture, Capture], exits: list[BaseException | None]
    ) -> None:
        await run(captures, "version")
        assert exits == [None]

    @pytest.mark.parametrize("file_stdout", [True, False])
    async def it_passes_files_through_and_drains_only_the_capture(
        tmp_path: Path, spawn: Mock, file_stdout: bool
    ) -> None:
        capture = Capture(101)
        with (tmp_path / "output").open("wb") as file:
            out, err = (file, capture) if file_stdout else (capture, file)
            assert await execute([], stdin=None, stdout=out, stderr=err) == 0  # type: ignore[arg-type]
            spawn.assert_called_once_with(
                "docker",
                stdin=None,
                stdout=file if file_stdout else capture.write,
                stderr=capture.write if file_stdout else file,
            )
            capture.release.assert_called_with()
            assert not file.closed
