import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from botbox.credential_proxy.stop_container import REMOVE_SECONDS, stop_container


@pytest.fixture
def steps() -> list[str]:
    return []


@pytest.fixture(autouse=True)
def stop(steps: list[str]) -> Iterator[AsyncMock]:
    with patch(
        f"{__package__}.stop_container.stop",
        side_effect=lambda name, seconds: steps.append(f"stop --time {seconds} {name}"),
    ) as m:
        yield m


@pytest.fixture(autouse=True)
def remove(steps: list[str]) -> Iterator[AsyncMock]:
    with patch(
        f"{__package__}.stop_container.remove", side_effect=lambda n: steps.append(f"rm {n}")
    ) as m:
        yield m


def exiting_on_stop(stop: AsyncMock, steps: list[str]) -> asyncio.Future[int]:
    client: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    def exit_on_stop(name: str, seconds: int) -> None:
        steps.append(f"stop --time {seconds} {name}")
        client.set_result(137)

    stop.side_effect = exit_on_stop
    return client


def describe_stop_container() -> None:
    def it_gives_the_daemon_30s() -> None:
        assert REMOVE_SECONDS == 30

    async def it_stops_the_container_then_removes_it(stop: AsyncMock, steps: list[str]) -> None:
        client = exiting_on_stop(stop, steps)
        await stop_container(client, "p")
        assert steps == ["stop --time 5 p", "rm p"]
        assert client.result() == 137

    async def it_kills_a_client_that_outlives_the_stop(steps: list[str]) -> None:
        client: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        with patch(f"{__package__}.stop_container.STOP_SECONDS", 0.01):
            await stop_container(client, "p")
        assert client.cancelled()
        assert steps == ["stop --time 0.01 p", "rm p"]

    async def it_warns_and_carries_on_when_docker_fails(remove: AsyncMock) -> None:
        client: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        client.set_result(0)
        remove.side_effect = RuntimeError("daemon gone")
        with pytest.warns(RuntimeWarning, match="remove its credential proxy p: daemon gone") as w:
            await stop_container(client, "p")
        assert w[0].filename == __file__

    async def it_gives_up_on_a_daemon_that_hangs(remove: AsyncMock) -> None:
        client: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        client.set_result(0)

        async def hang(_: str) -> None:
            await asyncio.Event().wait()

        remove.side_effect = hang
        with (
            patch(f"{__package__}.stop_container.REMOVE_SECONDS", 0.05),
            pytest.warns(RuntimeWarning, match="credential proxy p"),
        ):
            await stop_container(client, "p")
