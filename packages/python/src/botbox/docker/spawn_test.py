import asyncio
import sys
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from botbox.docker.spawn import spawn


@pytest.fixture(autouse=True)
def abandon() -> Iterator[AsyncMock]:
    with patch("botbox.docker.spawn.abandon", autospec=True) as m:
        yield m


@pytest.fixture
def exec_() -> Iterator[AsyncMock]:
    with patch("botbox.docker.spawn.asyncio.create_subprocess_exec", autospec=True) as m:
        yield m


def describe_spawn() -> None:
    @pytest.mark.usefixtures("exec_")
    async def it_takes_its_streams_by_keyword_only() -> None:
        with pytest.raises(TypeError):
            await spawn([], None, None, None)  # type: ignore[call-arg]

    async def it_runs_docker_with_the_args_in_a_session_of_its_own(exec_: AsyncMock) -> None:
        await spawn(
            ["version", "--format", "json"],
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=None,
        )
        exec_.assert_awaited_once_with(
            "docker",
            "version",
            "--format",
            "json",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=None,
            start_new_session=True,
        )

    async def it_returns_the_process(exec_: AsyncMock) -> None:
        assert await spawn([], stdin=None, stdout=None, stderr=None) is exec_.return_value

    def describe_cancelled_while_starting() -> None:
        @pytest.fixture
        def started(exec_: AsyncMock) -> asyncio.Event:
            started = asyncio.Event()

            async def slow(*_args: object, **_options: object) -> str:
                await started.wait()
                return "the process"

            exec_.side_effect = slow
            return started

        async def it_hands_the_spawn_to_abandon_and_raises(
            started: asyncio.Event, abandon: AsyncMock
        ) -> None:
            async def wait_out(starting: asyncio.Future[str]) -> None:
                started.set()
                assert await starting == "the process"

            abandon.side_effect = wait_out
            task = asyncio.create_task(spawn([], stdin=None, stdout=None, stderr=None))
            await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            abandon.assert_awaited_once()

        async def it_finishes_abandoning_through_a_second_cancel(
            started: asyncio.Event, abandon: AsyncMock
        ) -> None:
            finished = asyncio.Event()

            async def wait_out(starting: asyncio.Future[str]) -> None:
                await asyncio.sleep(0.05)
                started.set()
                await starting
                finished.set()

            abandon.side_effect = wait_out
            task = asyncio.create_task(spawn([], stdin=None, stdout=None, stderr=None))
            await asyncio.sleep(0.01)
            task.cancel()
            await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert finished.is_set()


def describe_process_imports() -> None:
    async def it_uses_the_relocated_helpers() -> None:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "from botbox.docker.spawn import abandon, settle; "
            'assert abandon.__module__ == "botbox.linux_tools.process.abandon"; '
            'assert settle.__module__ == "botbox.linux_tools.process.settle"; ',
        )
        assert await process.wait() == 0
