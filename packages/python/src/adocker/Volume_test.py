import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from adocker.Volume import REMOVE_SECONDS, Volume

CREATE = call("volume", "create", "--label", "botbox.run=x", "v")
REMOVE = call("volume", "rm", "--force", "v")


@pytest.fixture
def run_docker() -> Iterator[AsyncMock]:
    with (
        patch("adocker.Volume.run_docker", autospec=True) as m,
        patch("adocker.remove_volume.run_docker", m),
    ):
        yield m


def failing_removal(run_docker: AsyncMock, error: BaseException) -> None:
    async def docker(*args: str) -> str:
        if args[1] == "rm":
            raise error
        return ""

    run_docker.side_effect = docker


def describe_Volume() -> None:
    def it_gives_removal_thirty_seconds() -> None:
        assert REMOVE_SECONDS == 30

    async def it_creates_a_labelled_volume_yields_its_name_and_removes_it(
        run_docker: AsyncMock,
    ) -> None:
        async with Volume("v", labels={"botbox.run": "x"}) as volume:
            assert volume.name == "v"
            assert run_docker.await_args_list == [CREATE]
        assert run_docker.await_args_list == [CREATE, REMOVE]

    async def it_creates_an_unlabelled_volume_by_default(run_docker: AsyncMock) -> None:
        async with Volume("v"):
            assert run_docker.await_args_list == [call("volume", "create", "v")]

    async def it_removes_it_when_the_block_raises(run_docker: AsyncMock) -> None:
        with pytest.raises(KeyError):
            async with Volume("v", labels={"botbox.run": "x"}):
                raise KeyError
        assert run_docker.await_args_list == [CREATE, REMOVE]

    async def it_enters_nothing_when_creation_fails(run_docker: AsyncMock) -> None:
        run_docker.side_effect = RuntimeError("no space")
        with pytest.raises(RuntimeError, match="no space"):
            await Volume("v", labels={"botbox.run": "x"}).__aenter__()
        assert run_docker.await_args_list == [CREATE]

    async def it_raises_a_failed_removal_after_a_clean_block(run_docker: AsyncMock) -> None:
        failing_removal(run_docker, RuntimeError("in use"))
        with pytest.raises(RuntimeError, match="in use"):
            async with Volume("v", labels={"botbox.run": "x"}):
                pass

    async def it_keeps_the_blocks_error_over_a_failed_removal(run_docker: AsyncMock) -> None:
        failing_removal(run_docker, RuntimeError("in use"))
        with pytest.raises(KeyError):
            async with Volume("v", labels={"botbox.run": "x"}):
                raise KeyError

    async def it_hands_a_failed_removal_to_on_error(run_docker: AsyncMock) -> None:
        error = RuntimeError("in use")
        failing_removal(run_docker, error)
        on_error = Mock()
        async with Volume("v", labels={"botbox.run": "x"}, on_error=on_error):
            pass
        on_error.assert_called_once_with(error)

    async def it_gives_up_on_a_removal_that_outlasts_its_limit(run_docker: AsyncMock) -> None:
        async def docker(*args: str) -> str:
            if args[1] == "rm":
                await asyncio.sleep(3600)
            return ""

        run_docker.side_effect = docker
        with pytest.raises(TimeoutError, match=r"did not remove it within 0\.01s"):
            async with Volume("v", labels={"botbox.run": "x"}, remove_seconds=0.01):
                pass

    async def it_finishes_removing_through_a_cancel_then_raises_it(
        run_docker: AsyncMock,
    ) -> None:
        removing, release = asyncio.Event(), asyncio.Event()
        removed = Mock()

        async def docker(*args: str) -> str:
            if args[1] == "rm":
                removing.set()
                await release.wait()
                removed()
            return ""

        run_docker.side_effect = docker

        async def hold() -> None:
            async with Volume("v", labels={"botbox.run": "x"}):
                await asyncio.sleep(3600)

        task = asyncio.create_task(hold())
        await asyncio.sleep(0)
        task.cancel()
        await removing.wait()
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        removed.assert_called_once_with()

    async def it_hands_a_failed_removal_to_on_error_when_the_block_raises(
        run_docker: AsyncMock,
    ) -> None:
        error = RuntimeError("in use")
        failing_removal(run_docker, error)
        on_error = Mock()
        with pytest.raises(KeyError):
            async with Volume("v", labels={"botbox.run": "x"}, on_error=on_error):
                raise KeyError
        on_error.assert_called_once_with(error)

    def it_takes_its_options_by_keyword_only() -> None:
        with pytest.raises(TypeError):
            Volume("v", "botbox.run=x")  # type: ignore[call-arg]

    def it_mounts_by_name_read_write_unless_told() -> None:
        volume = Volume("v", labels={"botbox.run": "x"})
        assert volume.mount("/run/x") == ("v", "/run/x", "rw")
        assert volume.mount("/run/x", "ro") == ("v", "/run/x", "ro")
