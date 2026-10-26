import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from adocker.utils.execute import CHUNK_BYTES, execute

PIPE = asyncio.subprocess.PIPE


class Process:
    """A spawned client whose piped stdout and stderr are fed by the test."""

    def __init__(self, wait: AsyncMock, stdout: object, stderr: object) -> None:
        self.wait = wait
        self.kill = Mock(side_effect=self.close)
        self.stdout = asyncio.StreamReader() if stdout == PIPE else None
        self.stderr = asyncio.StreamReader() if stderr == PIPE else None

    def close(self, leftover: bytes = b"") -> None:
        """What a killed client does to its pipes: whatever it last wrote, then EOF."""
        for reader in (self.stdout, self.stderr):
            if reader is not None and not reader.at_eof():
                reader.feed_data(leftover)
                reader.feed_eof()

    def print(self, stdout: bytes = b"", stderr: bytes = b"") -> None:
        for reader, data in ((self.stdout, stdout), (self.stderr, stderr)):
            if reader is not None:
                if data:
                    reader.feed_data(data)
                reader.feed_eof()


@pytest.fixture
def wait() -> AsyncMock:
    return AsyncMock(return_value=0)


@pytest.fixture
def made() -> list[Process]:
    return []


@pytest.fixture
def exits() -> list[BaseException | None]:
    return []


@pytest.fixture
def printed() -> dict[str, bytes]:
    """What each spawned client prints and closes on spawning; empty for a held one."""
    return {"stdout": b"out", "stderr": b"err"}


@pytest.fixture(autouse=True)
def spawn(
    wait: AsyncMock,
    made: list[Process],
    exits: list[BaseException | None],
    printed: dict[str, bytes],
) -> Iterator[Mock]:
    @asynccontextmanager
    async def spawned(
        *_args: object, stdout: object, stderr: object, **_options: object
    ) -> AsyncIterator[Process]:
        process = Process(wait, stdout, stderr)
        made.append(process)
        if printed:
            process.print(**printed)
        try:
            yield process
        except BaseException as error:
            exits.append(error)
            raise
        exits.append(None)

    with patch("adocker.utils.execute.spawn", side_effect=spawned) as m:
        yield m


@pytest.fixture
def out() -> bytearray:
    return bytearray()


@pytest.fixture
def err() -> bytearray:
    return bytearray()


def describe_execute() -> None:
    async def it_takes_its_streams_by_keyword_only() -> None:
        with pytest.raises(TypeError):
            await execute(("version",), 7, None, None)  # type: ignore[call-arg]

    async def it_returns_the_clients_exit_code(wait: AsyncMock) -> None:
        wait.return_value = 3
        assert await execute(["rm", "x"], stdin=None, stdout=None, stderr=None) == 3

    async def it_pipes_each_sink_and_hands_it_every_chunk(
        spawn: Mock, out: bytearray, err: bytearray
    ) -> None:
        assert await execute(["build"], stdin=7, stdout=out.extend, stderr=err.extend) == 0
        spawn.assert_called_once_with("docker", "build", stdin=7, stdout=PIPE, stderr=PIPE)
        assert (bytes(out), bytes(err)) == (b"out", b"err")

    async def it_reads_in_bounded_chunks(made: list[Process], printed: dict[str, bytes]) -> None:
        printed.clear()
        chunks: list[int] = []
        task = asyncio.create_task(
            execute([], stdin=None, stdout=lambda chunk: chunks.append(len(chunk)), stderr=None)
        )
        await asyncio.sleep(0)
        made[0].print(stdout=b"x" * (CHUNK_BYTES + 1))
        await task
        assert chunks == [CHUNK_BYTES, 1]

    @pytest.mark.parametrize("file_stdout", [True, False])
    async def it_passes_files_through_and_pipes_only_the_sink(
        tmp_path: Path, spawn: Mock, err: bytearray, file_stdout: bool
    ) -> None:
        with (tmp_path / "output").open("wb") as file:
            stdout, stderr = (file, err.extend) if file_stdout else (err.extend, file)
            assert await execute([], stdin=None, stdout=stdout, stderr=stderr) == 0
            spawn.assert_called_once_with(
                "docker",
                stdin=None,
                stdout=file if file_stdout else PIPE,
                stderr=PIPE if file_stdout else file,
            )
            assert not file.closed
        assert bytes(err) == (b"err" if file_stdout else b"out")

    async def it_signals_started_once_the_client_is_spawned(wait: AsyncMock) -> None:
        started: asyncio.Future[None] = asyncio.get_running_loop().create_future()

        async def waited() -> int:
            assert started.done()
            return 0

        wait.side_effect = waited
        await execute([], stdin=None, stdout=None, stderr=None, started=started)
        assert started.result() is None

    async def it_leaves_started_alone_when_the_spawn_fails(spawn: Mock) -> None:
        started: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        spawn.side_effect = FileNotFoundError("docker")
        with pytest.raises(FileNotFoundError):
            await execute([], stdin=None, stdout=None, stderr=None, started=started)
        assert not started.done()

    async def it_returns_only_once_the_output_is_in(
        made: list[Process], printed: dict[str, bytes], out: bytearray
    ) -> None:
        printed.clear()
        task = asyncio.create_task(execute([], stdin=None, stdout=out.extend, stderr=None))
        await asyncio.sleep(0.01)
        made[0].wait.assert_awaited_once_with()
        assert not task.done()
        made[0].print(stdout=b"late")
        assert await task == 0
        assert bytes(out) == b"late"

    async def it_raises_what_a_sink_raised_once_the_client_is_killed_and_reaped(
        made: list[Process], exits: list[BaseException | None]
    ) -> None:
        def full(_chunk: bytes) -> None:
            raise OSError("disk full")

        with pytest.raises(OSError, match="disk full"):
            await execute([], stdin=None, stdout=full, stderr=None)
        made[0].kill.assert_called_once_with()
        assert made[0].wait.await_count == 2
        assert [type(error) for error in exits] == [OSError]

    async def it_drains_the_other_stream_to_its_sink_when_a_sink_raises(
        made: list[Process], printed: dict[str, bytes], err: bytearray
    ) -> None:
        printed.clear()

        def full(_chunk: bytes) -> None:
            raise OSError("disk full")

        task = asyncio.create_task(execute([], stdin=None, stdout=full, stderr=err.extend))
        await asyncio.sleep(0)
        made[0].kill.side_effect = lambda: made[0].close(b"after")
        assert made[0].stdout is not None
        made[0].stdout.feed_data(b"x")
        with pytest.raises(OSError, match="disk full"):
            await task
        assert err == b"after"

    async def it_kills_and_waits_out_the_client_when_cancelled_while_it_runs(
        wait: AsyncMock, made: list[Process], exits: list[BaseException | None]
    ) -> None:
        running = asyncio.Event()

        async def waited() -> int:
            if not running.is_set():
                running.set()
                await asyncio.Event().wait()
            assert made[0].kill.called
            return -9

        wait.side_effect = waited
        task = asyncio.create_task(execute([], stdin=None, stdout=None, stderr=None))
        await running.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        made[0].kill.assert_called_once_with()
        assert wait.await_count == 2
        assert [type(error) for error in exits] == [asyncio.CancelledError]

    async def it_kills_the_client_when_waiting_on_it_fails(
        wait: AsyncMock, made: list[Process]
    ) -> None:
        wait.side_effect = [OSError("wait failed"), -9]
        with pytest.raises(OSError, match="wait failed"):
            await execute([], stdin=None, stdout=None, stderr=None)
        made[0].kill.assert_called_once_with()

    async def it_tolerates_a_client_that_is_already_gone_when_killed(
        made: list[Process], printed: dict[str, bytes], out: bytearray
    ) -> None:
        printed.clear()
        task = asyncio.create_task(execute([], stdin=None, stdout=out.extend, stderr=None))
        await asyncio.sleep(0.01)

        def gone() -> None:
            made[0].close()
            raise ProcessLookupError

        made[0].kill.side_effect = gone
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        made[0].kill.assert_called_once_with()

    async def it_leaves_the_client_alone_when_docker_finishes(
        made: list[Process], exits: list[BaseException | None], out: bytearray
    ) -> None:
        await execute([], stdin=None, stdout=out.extend, stderr=None)
        made[0].kill.assert_not_called()
        assert exits == [None]

    async def it_hands_the_sinks_what_a_killed_client_left_in_its_pipes(
        made: list[Process], printed: dict[str, bytes], out: bytearray, err: bytearray
    ) -> None:
        printed.clear()
        task = asyncio.create_task(execute([], stdin=None, stdout=out.extend, stderr=err.extend))
        await asyncio.sleep(0.01)
        made[0].kill.side_effect = lambda: made[0].close(b"x" * 3 * CHUNK_BYTES)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (bytes(out), bytes(err)) == (b"x" * 3 * CHUNK_BYTES, b"x" * 3 * CHUNK_BYTES)
        assert made[0].stdout is not None
        assert made[0].stdout.at_eof()

    async def it_keeps_output_that_arrived_just_before_a_cancel(
        made: list[Process], printed: dict[str, bytes], out: bytearray
    ) -> None:
        printed.clear()
        task = asyncio.create_task(execute([], stdin=None, stdout=out.extend, stderr=None))
        await asyncio.sleep(0.01)
        assert made[0].stdout is not None
        made[0].stdout.feed_data(b"partial\n")
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert bytes(out) == b"partial\n"

    async def it_reaps_the_client_through_another_cancel(
        made: list[Process], printed: dict[str, bytes], out: bytearray
    ) -> None:
        printed.clear()
        task = asyncio.create_task(execute([], stdin=None, stdout=out.extend, stderr=None))
        await asyncio.sleep(0.01)
        made[0].kill.side_effect = None
        task.cancel()
        await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done()
        made[0].close()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert made[0].wait.await_count == 2
