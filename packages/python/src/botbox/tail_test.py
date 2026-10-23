import asyncio
from pathlib import Path

import pytest

from botbox.tail import tail


def describe_tail() -> None:
    async def it_reads_existing_and_new_lines(tmp_path: Path) -> None:
        path = tmp_path / "stdout.txt"
        path.write_bytes(b"before\n")
        async with asyncio.timeout(5), tail(path) as reader:
            assert await reader.readline() == b"before\n"
            with path.open("ab") as writer:
                writer.write(b"after\n")
            assert await reader.readline() == b"after\n"
        assert reader.at_eof()

    async def it_closes_the_pipe_when_cancelled(tmp_path: Path) -> None:
        path = tmp_path / "stdout.txt"
        path.touch()
        started = asyncio.Event()
        readers: list[asyncio.StreamReader] = []

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


def describe_startup() -> None:
    async def it_reaps_a_spawn_that_is_cancelled_before_its_handle_arrives(tmp_path: Path) -> None:
        from unittest.mock import AsyncMock, patch

        started = asyncio.Event()
        release = asyncio.Event()
        process = AsyncMock()

        async def spawn(*_args: object, **_kwargs: object) -> AsyncMock:
            started.set()
            await release.wait()
            return process

        async def abandon(starting: asyncio.Future[AsyncMock]) -> None:
            release.set()
            assert await starting is process

        async def follow() -> None:
            async with tail(tmp_path / "stdout.txt"):
                pytest.fail("cancelled spawn must not yield")

        with (
            patch("botbox.tail.asyncio.create_subprocess_exec", side_effect=spawn),
            patch("botbox.tail.abandon", side_effect=abandon) as abandoned,
        ):
            task = asyncio.create_task(follow())
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            abandoned.assert_awaited_once()
