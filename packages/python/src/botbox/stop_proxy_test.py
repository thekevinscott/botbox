import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, Mock, patch

import pytest

from adocker import Container
from botbox.stop_proxy import stop_proxy


@pytest.fixture
def steps() -> list[str]:
    return []


@pytest.fixture
def stdin(steps: list[str]) -> Mock:
    stdin = Mock()
    stdin.close.side_effect = lambda: steps.append("close stdin")
    return stdin


@pytest.fixture(autouse=True)
def remove() -> Iterator[Mock]:
    with patch("botbox.stop_proxy.remove_within", Mock(return_value="removal")) as m:
        yield m


@pytest.fixture(autouse=True)
def warned(steps: list[str]) -> Iterator[AsyncMock]:
    async def step(removal: str, what: str) -> None:
        steps.append(f"{removal}: {what}")

    with patch("botbox.stop_proxy.warned", autospec=True, side_effect=step) as m:
        yield m


def client_ending_on(stdin: Mock) -> asyncio.Task[int]:
    """A client that exits 0 once its stdin is closed."""
    closed = asyncio.Event()
    stdin.close.side_effect = closed.set

    async def attached() -> int:
        await closed.wait()
        return 0

    return asyncio.ensure_future(attached())


def proxy(client: "asyncio.Future[int]") -> Container:
    return Container("botbox-proxy-1", client=client)  # type: ignore[arg-type]


def describe_stop_proxy() -> None:
    async def it_closes_stdin_waits_for_the_client_then_removes_the_proxy(
        stdin: Mock, steps: list[str], remove: Mock
    ) -> None:
        client = client_ending_on(stdin)
        await stop_proxy(proxy(client), stdin, 10)
        assert client.result() == 0
        remove.assert_called_once_with("botbox-proxy-1")
        assert steps == ["removal: remove its proxy botbox-proxy-1"]

    async def it_cancels_a_client_that_outlives_the_grace(stdin: Mock) -> None:
        client = asyncio.ensure_future(asyncio.Event().wait())
        await stop_proxy(proxy(client), stdin, 0.01)  # type: ignore[arg-type]
        assert client.cancelled()

    async def it_waits_the_grace_before_cancelling(stdin: Mock) -> None:
        client = asyncio.ensure_future(asyncio.sleep(0.05, result=0))
        await stop_proxy(proxy(client), stdin, 1)
        assert client.result() == 0

    async def it_takes_a_client_that_failed_without_raising(stdin: Mock, steps: list[str]) -> None:
        async def failed() -> int:
            raise FileNotFoundError("docker")

        client = asyncio.ensure_future(failed())
        await stop_proxy(proxy(client), stdin, 10)
        assert steps == ["close stdin", "removal: remove its proxy botbox-proxy-1"]
