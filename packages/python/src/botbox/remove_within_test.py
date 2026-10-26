import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from botbox.remove_within import REMOVE_SECONDS, remove_within


@pytest.fixture
def container() -> Mock:
    return Mock(remove=AsyncMock())


@pytest.fixture
def remove(container: Mock) -> AsyncMock:
    remove: AsyncMock = container.remove
    return remove


def describe_remove_within() -> None:
    def it_gives_the_daemon_thirty_seconds() -> None:
        assert REMOVE_SECONDS == 30

    async def it_removes_the_container(container: Mock, remove: AsyncMock) -> None:
        await remove_within(container)
        remove.assert_awaited_once_with()

    async def it_waits_for_a_removal_inside_its_deadline(
        container: Mock, remove: AsyncMock
    ) -> None:
        done = asyncio.Event()

        async def slow() -> None:
            await asyncio.sleep(0.02)
            done.set()

        remove.side_effect = slow
        await remove_within(container, 1)
        assert done.is_set()

    async def it_cancels_a_removal_that_outlives_its_deadline(
        container: Mock, remove: AsyncMock
    ) -> None:
        cancelled = asyncio.Event()

        async def hung() -> None:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        remove.side_effect = hung
        with pytest.raises(TimeoutError, match=r"^the daemon did not remove it within 0\.01s$"):
            await remove_within(container, 0.01)
        assert cancelled.is_set()

    async def it_raises_a_removal_that_fails(container: Mock, remove: AsyncMock) -> None:
        remove.side_effect = OSError("daemon gone")
        with pytest.raises(OSError, match="daemon gone"):
            await remove_within(container)
