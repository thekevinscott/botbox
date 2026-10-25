import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ._close import _close


@pytest.fixture
def process() -> Mock:
    return Mock(stdin=None, stdout=None, stderr=None, returncode=None, pid=42)


@pytest.fixture(autouse=True)
def reap() -> Iterator[AsyncMock]:
    with patch(f"{__package__}._close.reap", autospec=True) as m:
        yield m


@pytest.fixture(autouse=True)
def ended() -> Iterator[AsyncMock]:
    with patch(f"{__package__}._close.ended", autospec=True) as m:
        yield m


@pytest.fixture(autouse=True)
def group_running() -> Iterator[Mock]:
    with patch(f"{__package__}._close.group_running", return_value=False) as m:
        yield m


def describe_close() -> None:
    @pytest.mark.parametrize("expires", [False, True])
    async def it_closes_stdin_then_lingers_before_reaping(
        process: Mock, reap: AsyncMock, ended: AsyncMock, expires: bool
    ) -> None:
        process.stdin = Mock()

        async def wait(*_args: object) -> None:
            process.stdin.close.assert_called_once_with()
            if expires:
                await asyncio.Event().wait()

        ended.side_effect = wait
        await _close(process, (), signum=9, grace=0.1, linger=0.01)
        ended.assert_awaited_once_with(process, ())
        assert reap.await_count == int(expires)

    @pytest.mark.parametrize("error", [OSError("wait"), asyncio.CancelledError()])
    async def it_reaps_when_the_linger_wait_fails(
        process: Mock, reap: AsyncMock, ended: AsyncMock, error: BaseException
    ) -> None:
        ended.side_effect = error
        with pytest.raises(type(error)):
            await _close(process, (), signum=9, grace=0.1, linger=2)
        reap.assert_awaited_once()

    @pytest.mark.parametrize("eof", [False, True])
    async def it_drains_or_cancels_owned_readers(process: Mock, reap: AsyncMock, eof: bool) -> None:
        process.stdout = asyncio.StreamReader()
        process.stdout.feed_data(b"output")
        if eof:
            process.stdout.feed_eof()

        async def draining(_process: Mock, *drains: asyncio.Future[object], **_kw: object) -> None:
            assert len(drains) == 1
            if eof:
                await asyncio.gather(*drains)

        reap.side_effect = draining
        await _close(process, (), signum=9, grace=0.1, linger=0)
        reader = reap.await_args_list[0].args[1]
        assert reader.done()
        assert process.stdout.at_eof() if eof else reader.cancelled()

    @pytest.mark.parametrize(
        "state",
        [(0, False, True), (None, False, True), (0, True, True), (0, False, False)],
    )
    async def it_skips_reaping_only_when_everything_has_finished(
        process: Mock,
        reap: AsyncMock,
        group_running: Mock,
        state: tuple[int | None, bool, bool],
    ) -> None:
        code, running, done = state
        process.returncode, group_running.return_value = code, running
        drain = asyncio.get_running_loop().create_future()
        if done:
            drain.set_result(None)
        await _close(process, (drain,), signum=9, grace=0.1, linger=0)
        if code is not None and not running and done:
            reap.assert_not_awaited()
        else:
            reap.assert_awaited_once_with(process, drain, signum=9, grace=0.1)
        assert not drain.cancelled()
