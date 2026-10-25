import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ._close import _close


@pytest.fixture
def process() -> Mock:
    return Mock(stdout=None, stderr=None)


@pytest.fixture(autouse=True)
def reap() -> Iterator[AsyncMock]:
    with patch(f"{__package__}._close.reap", autospec=True) as m:
        yield m


@pytest.fixture(autouse=True)
def ended() -> Iterator[AsyncMock]:
    with patch(f"{__package__}._close.ended", autospec=True) as m:
        yield m


async def close(process: Mock, *, linger: float = 0) -> None:
    await _close(process, (), signum=9, grace=0.1, linger=linger)


def describe_close() -> None:
    async def it_requires_keyword_cleanup_options(process: Mock) -> None:
        with pytest.raises(TypeError):
            await _close(process, (), 9, 0.1, 0)  # type: ignore[call-arg]

    async def it_forwards_the_signal_grace_and_external_drains(
        process: Mock, reap: AsyncMock, ended: AsyncMock
    ) -> None:
        drain = asyncio.get_running_loop().create_future()
        await _close(process, (drain,), signum=9, grace=0.1, linger=0)
        reap.assert_awaited_once_with(process, drain, signum=9, grace=0.1)
        ended.assert_not_awaited()
        assert not drain.cancelled()

    async def it_leaves_naturally_completed_groups_alone(
        process: Mock, reap: AsyncMock, ended: AsyncMock
    ) -> None:
        await close(process, linger=2)
        ended.assert_awaited_once_with(process, ())
        reap.assert_not_awaited()

    async def it_stops_groups_after_linger_expires(
        process: Mock, reap: AsyncMock, ended: AsyncMock
    ) -> None:
        async def blocked(*_args: object) -> None:
            await asyncio.Event().wait()

        ended.side_effect = blocked
        await close(process, linger=0.01)
        reap.assert_awaited_once_with(process, signum=9, grace=0.1)

    async def it_reaps_when_the_linger_wait_fails(
        process: Mock, reap: AsyncMock, ended: AsyncMock
    ) -> None:
        ended.side_effect = OSError("wait")
        with pytest.raises(OSError, match="wait"):
            await close(process, linger=2)
        reap.assert_awaited_once()

    async def it_drains_and_joins_owned_pipes(process: Mock, reap: AsyncMock) -> None:
        process.stdout = asyncio.StreamReader()
        process.stderr = asyncio.StreamReader()
        process.stdout.feed_data(b"output")
        process.stdout.feed_eof()
        process.stderr.feed_data(b"error")
        process.stderr.feed_eof()

        async def draining(_process: Mock, *drains: asyncio.Future[object], **_kw: object) -> None:
            assert len(drains) == 2
            await asyncio.gather(*drains)

        reap.side_effect = draining
        await close(process)
        assert process.stdout.at_eof() and process.stderr.at_eof()

    async def it_cancels_readers_of_pipes_that_never_close(process: Mock, reap: AsyncMock) -> None:
        process.stdout = asyncio.StreamReader()
        await close(process)
        assert reap.await_args is not None
        reader = reap.await_args.args[1]
        assert reader.cancelled()

    async def it_finishes_reaping_despite_repeated_cancels(
        process: Mock, reap: AsyncMock, ended: AsyncMock
    ) -> None:
        waiting = asyncio.Event()
        stopping = asyncio.Event()
        release = asyncio.Event()
        done = asyncio.Event()

        async def wait(*_args: object) -> None:
            waiting.set()
            await asyncio.Event().wait()

        async def stop(*_args: object, **_kwargs: object) -> None:
            stopping.set()
            await release.wait()
            done.set()

        ended.side_effect = wait
        reap.side_effect = stop
        task = asyncio.create_task(close(process, linger=10))
        await waiting.wait()
        task.cancel()
        await stopping.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not done.is_set()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert done.is_set()
