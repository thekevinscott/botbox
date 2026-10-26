import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from botbox.credential_proxy.stop_container import stop_container


@pytest.fixture
def steps() -> list[str]:
    return []


@pytest.fixture(autouse=True)
def run_docker(steps: list[str]) -> Iterator[AsyncMock]:
    with patch(
        f"{__package__}.stop_container.run_docker",
        side_effect=lambda *args: steps.append(" ".join(args)),
    ) as m:
        yield m


@pytest.fixture(autouse=True)
def remove(steps: list[str]) -> Iterator[AsyncMock]:
    with patch(
        f"{__package__}.stop_container.remove", side_effect=lambda n: steps.append(f"rm {n}")
    ) as m:
        yield m


def exiting_on_stop(run_docker: AsyncMock, steps: list[str]) -> asyncio.Future[int]:
    client: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    def stop(*args: str) -> None:
        steps.append(" ".join(args))
        client.set_result(137)

    run_docker.side_effect = stop
    return client


def describe_stop_container() -> None:
    async def it_stops_the_container_then_removes_it(
        run_docker: AsyncMock, steps: list[str]
    ) -> None:
        client = exiting_on_stop(run_docker, steps)
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
        with pytest.warns(RuntimeWarning, match="remove its credential proxy p: daemon gone"):
            await stop_container(client, "p")

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
