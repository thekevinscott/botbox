import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from botbox.remove_within import REMOVE_SECONDS, remove_within


@pytest.fixture(autouse=True)
def remove() -> Iterator[AsyncMock]:
    with patch("botbox.remove_within.remove", autospec=True) as m:
        yield m


def describe_remove_within() -> None:
    def it_gives_the_daemon_thirty_seconds() -> None:
        assert REMOVE_SECONDS == 30

    async def it_removes_the_container(remove: AsyncMock) -> None:
        await remove_within("botbox-agent-1")
        remove.assert_awaited_once_with("botbox-agent-1")

    async def it_waits_for_a_removal_inside_its_deadline(remove: AsyncMock) -> None:
        done = asyncio.Event()

        async def slow(_container: str) -> None:
            await asyncio.sleep(0.02)
            done.set()

        remove.side_effect = slow
        await remove_within("botbox-agent-1", 1)
        assert done.is_set()

    async def it_cancels_a_removal_that_outlives_its_deadline(remove: AsyncMock) -> None:
        cancelled = asyncio.Event()

        async def hung(_container: str) -> None:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        remove.side_effect = hung
        with pytest.raises(TimeoutError, match=r"^the daemon did not remove it within 0\.01s$"):
            await remove_within("botbox-agent-1", 0.01)
        assert cancelled.is_set()

    async def it_raises_a_removal_that_fails(remove: AsyncMock) -> None:
        remove.side_effect = OSError("daemon gone")
        with pytest.raises(OSError, match="daemon gone"):
            await remove_within("botbox-agent-1")
