from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from botbox.wait_for_proxy import POLL, wait_for_proxy

OUTPUT = bytearray(b"tinyproxy: bad config\xff\n")


@pytest.fixture(autouse=True)
def clock() -> Iterator[MagicMock]:
    with patch("botbox.wait_for_proxy.time", autospec=True) as m:
        m.monotonic.return_value = 0
        yield m


@pytest.fixture(autouse=True)
def sleep() -> Iterator[AsyncMock]:
    with patch("botbox.wait_for_proxy.asyncio.sleep", autospec=True) as m:
        yield m


@pytest.fixture
def client() -> Mock:
    client = Mock()
    client.done.return_value = False
    client.exception.return_value = None
    return client


@pytest.fixture
def socket(tmp_path: Path) -> Path:
    return tmp_path / "proxy.sock"


def describe_wait_for_proxy() -> None:
    def it_polls_every_fifty_milliseconds() -> None:
        assert POLL == 0.05

    async def it_returns_at_once_when_the_socket_is_there(
        socket: Path, client: Mock, sleep: AsyncMock
    ) -> None:
        socket.touch()
        await wait_for_proxy(socket, client, OUTPUT, 30)
        sleep.assert_not_awaited()

    async def it_polls_until_the_socket_appears(
        socket: Path, client: Mock, sleep: AsyncMock
    ) -> None:
        async def appear(_seconds: float) -> None:
            socket.touch()

        sleep.side_effect = appear
        await wait_for_proxy(socket, client, OUTPUT, 30)
        sleep.assert_awaited_once_with(POLL)

    async def it_raises_with_the_output_when_the_client_exits_first(
        socket: Path, client: Mock
    ) -> None:
        client.done.return_value = True
        with pytest.raises(RuntimeError) as raised:
            await wait_for_proxy(socket, client, OUTPUT, 30)
        assert str(raised.value) == "botbox proxy did not start:\ntinyproxy: bad config\ufffd\n"

    async def it_raises_from_what_the_client_raised(socket: Path, client: Mock) -> None:
        client.done.return_value = True
        client.exception.return_value = FileNotFoundError("docker")
        with pytest.raises(RuntimeError) as raised:
            await wait_for_proxy(socket, client, OUTPUT, 30)
        assert raised.value.__cause__ is client.exception.return_value

    async def it_raises_once_the_timeout_passes(
        socket: Path, client: Mock, clock: MagicMock, sleep: AsyncMock
    ) -> None:
        clock.monotonic.side_effect = [100.0, 129.0, 130.0, 130.5]
        with pytest.raises(RuntimeError, match="did not start") as raised:
            await wait_for_proxy(socket, client, OUTPUT, 30)
        assert raised.value.__cause__ is None
        assert sleep.await_count == 2
        client.exception.assert_not_called()
