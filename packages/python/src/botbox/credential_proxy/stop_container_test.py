import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from botbox.credential_proxy.stop_container import REMOVE_SECONDS, stop_container


@pytest.fixture
def steps() -> list[str]:
    return []


@pytest.fixture
async def client() -> "asyncio.Future[int]":
    return asyncio.get_running_loop().create_future()


@pytest.fixture
def container(steps: list[str], client: "asyncio.Future[int]") -> Mock:
    async def wait() -> int:
        return await client

    container = Mock(spec_set=["name", "stop", "remove", "wait"])
    container.name = "p"
    container.stop = AsyncMock(side_effect=lambda seconds: steps.append(f"stop --time {seconds}"))
    container.remove = AsyncMock(side_effect=lambda: steps.append("rm"))
    container.wait = wait
    return container


def describe_stop_container() -> None:
    def it_gives_the_daemon_30s() -> None:
        assert REMOVE_SECONDS == 30

    async def it_stops_the_container_then_removes_it(
        container: Mock, client: "asyncio.Future[int]", steps: list[str]
    ) -> None:
        container.stop.side_effect = lambda seconds: (
            steps.append(f"stop --time {seconds}"),
            client.set_result(137),
        )
        await stop_container(container)
        assert steps == ["stop --time 5", "rm"]
        assert client.result() == 137

    async def it_kills_a_client_that_outlives_the_stop(
        container: Mock, client: "asyncio.Future[int]", steps: list[str]
    ) -> None:
        with patch(f"{__package__}.stop_container.STOP_SECONDS", 0.01):
            await stop_container(container)
        assert client.cancelled()
        assert steps == ["stop --time 0.01", "rm"]

    async def it_removes_after_a_client_that_failed(
        container: Mock, client: "asyncio.Future[int]", steps: list[str]
    ) -> None:
        client.set_exception(OSError("docker"))
        await stop_container(container)
        assert steps == ["stop --time 5", "rm"]

    async def it_warns_and_carries_on_when_docker_fails(
        container: Mock, client: "asyncio.Future[int]"
    ) -> None:
        client.set_result(0)
        container.remove.side_effect = RuntimeError("daemon gone")
        with pytest.warns(RuntimeWarning, match="remove its credential proxy p: daemon gone") as w:
            await stop_container(container)
        assert w[0].filename == __file__

    async def it_gives_up_on_a_daemon_that_hangs(
        container: Mock, client: "asyncio.Future[int]"
    ) -> None:
        client.set_result(0)

        async def hang() -> None:
            await asyncio.Event().wait()

        container.remove.side_effect = hang
        with (
            patch(f"{__package__}.stop_container.REMOVE_SECONDS", 0.05),
            pytest.warns(RuntimeWarning, match="credential proxy p"),
        ):
            await stop_container(container)
