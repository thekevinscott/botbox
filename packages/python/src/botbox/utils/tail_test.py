import asyncio
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, patch

import pytest

from botbox.utils.tail import tail

if TYPE_CHECKING:
    from botbox.utils.LineReader import LineReader


@pytest.fixture
def lifetimes() -> Iterator[list[IO[bytes]]]:
    pipes: list[IO[bytes]] = []

    @contextmanager
    def own(pipe: IO[bytes]) -> Iterator[None]:
        pipes.append(pipe)
        yield

    with patch("botbox.utils.tail.owner_only", own, create=True):
        yield pipes


@pytest.fixture
def spawned() -> Iterator[list[asyncio.subprocess.Process]]:
    processes: list[asyncio.subprocess.Process] = []
    original = asyncio.create_subprocess_exec

    async def spawn(*args: str, **kwargs: object) -> asyncio.subprocess.Process:
        process = await original(*args, **kwargs)  # type: ignore[arg-type]
        processes.append(process)
        return process

    with patch("botbox.utils.tail.asyncio.create_subprocess_exec", side_effect=spawn):
        yield processes


@pytest.fixture
def starting() -> asyncio.Event:
    return asyncio.Event()


@pytest.fixture
def release() -> asyncio.Event:
    return asyncio.Event()


@pytest.fixture
def process() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def delayed_spawn(
    starting: asyncio.Event, release: asyncio.Event, process: AsyncMock
) -> Iterator[None]:
    async def spawn(*_args: object, **_kwargs: object) -> AsyncMock:
        starting.set()
        await release.wait()
        return process

    with patch("botbox.utils.tail.asyncio.create_subprocess_exec", side_effect=spawn):
        yield


@pytest.fixture
def abandoned(release: asyncio.Event, process: AsyncMock) -> Iterator[Mock]:
    async def abandon(started: asyncio.Future[AsyncMock]) -> None:
        release.set()
        assert await started is process

    with patch("botbox.utils.tail.abandon", side_effect=abandon) as mocked:
        yield mocked


def describe_tail() -> None:
    async def it_pauses_the_transport_when_the_consumer_stops_reading(
        tmp_path: Path, spawned: list[asyncio.subprocess.Process], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Bound the single pipe read that can overshoot the pause threshold.
        monkeypatch.setattr("asyncio.unix_events._UnixReadPipeTransport.max_size", 8192)
        path = tmp_path / "stdout.txt"
        path.write_bytes(b"line\n" * 1_000_000)
        async with asyncio.timeout(5), tail(path):
            stdout = spawned[0].stdout
            assert stdout is not None
            # StreamReader exposes no public transport accessor.
            transport = stdout._transport  # type: ignore[attr-defined]  # noqa: SLF001
            while transport.is_reading():
                await asyncio.sleep(0.01)
            assert stdout._paused  # type: ignore[attr-defined]  # noqa: SLF001
            assert spawned[0].returncode is None
            assert not stdout.at_eof()
            # Pausing happens after a pipe read crosses twice the default limit.
            assert len(stdout._buffer) <= 2 * 2**16 + 8192  # type: ignore[attr-defined]  # noqa: SLF001

    async def it_follows_a_relative_path_starting_with_a_dash(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        path = Path("-stdout.txt")
        path.write_bytes(b"before\n")
        async with asyncio.timeout(5), tail(path) as reader:
            assert await reader.readline() == b"before\n"
            with path.open("ab") as writer:
                writer.write(b"after\n")
            assert await reader.readline() == b"after\n"

    async def it_holds_a_lifetime_pipe_owner_only_until_teardown(
        tmp_path: Path,
        lifetimes: list[IO[bytes]],
    ) -> None:
        path = tmp_path / "stdout.txt"
        path.touch()
        async with tail(path):
            assert len(lifetimes) == 1
            assert not lifetimes[0].closed
        assert lifetimes[0].closed

    async def it_reads_existing_and_new_lines(tmp_path: Path) -> None:
        path = tmp_path / "stdout.txt"
        path.write_bytes(b"before\n")
        async with asyncio.timeout(5), tail(path) as reader:
            assert await reader.readline() == b"before\n"
            with path.open("ab") as writer:
                writer.write(b"after\n")
            assert await reader.readline() == b"after\n"
        assert reader.at_eof()

    async def it_preserves_large_line_boundaries_for_existing_and_new_output(
        tmp_path: Path,
    ) -> None:
        path = tmp_path / "stdout.txt"
        large = b"x" * 200_000 + b"\n"
        path.write_bytes(large + b"after existing\n")
        async with asyncio.timeout(5), tail(path) as reader:
            assert await reader.readline() == large
            assert await reader.readline() == b"after existing\n"
            with path.open("ab") as writer:
                writer.write(large + b"after appended\n")
            assert await reader.readline() == large
            assert await reader.readline() == b"after appended\n"

    async def it_exits_when_cancelled(
        tmp_path: Path, spawned: list[asyncio.subprocess.Process]
    ) -> None:
        path = tmp_path / "stdout.txt"
        path.touch()
        started = asyncio.Event()
        readers: list[LineReader] = []

        async def follow() -> None:
            async with tail(path) as reader:
                readers.append(reader)
                started.set()
                await reader.readline()

        task = asyncio.create_task(follow())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert readers[0].at_eof()
        assert spawned[0].returncode is not None

    async def it_follows_a_file_created_after_startup(tmp_path: Path) -> None:
        path = tmp_path / "later.txt"
        async with asyncio.timeout(10), tail(path) as reader:
            await asyncio.sleep(0.1)
            path.write_bytes(b"created\n")
            assert await reader.readline() == b"created\n"


def describe_startup() -> None:
    @pytest.mark.usefixtures("delayed_spawn")
    async def it_reaps_a_spawn_that_is_cancelled_before_its_handle_arrives(
        tmp_path: Path,
        starting: asyncio.Event,
        abandoned: Mock,
    ) -> None:
        async def follow() -> None:
            async with tail(tmp_path / "stdout.txt"):
                pytest.fail("cancelled spawn must not yield")

        task = asyncio.create_task(follow())
        await starting.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        abandoned.assert_awaited_once()


def describe_process_imports() -> None:
    async def it_uses_the_relocated_helpers() -> None:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "from botbox.utils.tail import abandon, discard, reap, settle, owner_only; "
            'assert abandon.__module__ == "botbox.posix_tools.process.abandon"; '
            'assert discard.__module__ == "botbox.posix_tools.process.discard"; '
            'assert reap.__module__ == "botbox.posix_tools.process.reap"; '
            'assert settle.__module__ == "botbox.posix_tools.process.settle"; '
            'assert owner_only.__module__ == "botbox.posix_tools.process.owner_only"; ',
        )
        assert await process.wait() == 0
