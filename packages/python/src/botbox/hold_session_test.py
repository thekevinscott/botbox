import asyncio
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from botbox.hold_session import hold_session

KILL = object()


def open_fds() -> set[str]:
    return {fd.name for fd in Path("/proc/self/fd").iterdir()}


class Client:
    """The attached `docker run`: what it was given, and a CLI that echoes each line it reads."""

    def __init__(self) -> None:
        self.args: list[str] = []
        self.options: dict[str, Any] = {}
        self.cancelled = False
        self.fails: BaseException | None = None

    async def __call__(self, args: list[str], **options: Any) -> int:
        self.args, self.options = args, options
        out, err = options["stdout"], options["stderr"]
        reader = asyncio.StreamReader()
        pipe = os.fdopen(os.dup(options["stdin"]), "rb")
        transport, _ = await asyncio.get_running_loop().connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(reader), pipe
        )
        try:
            if self.fails is not None:
                raise self.fails
            while line := await reader.readline():
                os.write(out.write, line)
            os.write(err.write, b"bye\n")
            out.release()
            err.release()
            await asyncio.gather(out.eof, err.eof)
            return 7
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        finally:
            out.release()
            err.release()
            transport.close()


@pytest.fixture(autouse=True)
def client() -> Iterator[Client]:
    client = Client()
    with patch("botbox.hold_session.execute", client):
        yield client


@pytest.fixture(autouse=True)
def signal() -> Iterator[Mock]:
    with patch("botbox.hold_session.signal", autospec=True) as m:
        m.SIGKILL = KILL
        yield m


@pytest.fixture(autouse=True)
def owner_only() -> Iterator[MagicMock]:
    with patch("botbox.hold_session.owner_only", autospec=True) as m:
        yield m


@pytest.fixture
def agent() -> Mock:
    return Mock(encode=lambda message: message, turn_ended=lambda event: event == {"type": "end"})


def describe_hold_session() -> None:
    async def it_starts_the_attached_run_with_its_args(client: Client, agent: Mock) -> None:
        async with hold_session(agent, ["--interactive", "img"]) as live:
            await asyncio.sleep(0.01)
            assert client.args == ["run", "--interactive", "img"]
            assert client.options["signum"] is KILL
            assert live.agent is agent
            assert client.options["stdout"] is live.stdout
            assert client.options["stderr"].into is live.stderr
            live.stdin.close()
            await live.client

    async def it_streams_the_clis_output_back_to_the_session(agent: Mock) -> None:
        async with hold_session(agent, []) as live:
            assert await live.message('{"type": "end"}') == [{"type": "end"}]
            live.stdin.close()
            assert await live.client == 7
        assert live.stdout.into == b'{"type": "end"}\n'
        assert live.stderr == b"bye\n"

    async def it_holds_the_input_for_this_process_alone(agent: Mock, owner_only: MagicMock) -> None:
        async with hold_session(agent, []) as live:
            owner_only.assert_called_once_with(live.stdin.transport.get_extra_info("pipe"))
            owner_only.return_value.__exit__.assert_not_called()
        owner_only.return_value.__exit__.assert_called_once()

    async def it_kills_the_client_if_it_is_still_running_on_leaving(
        client: Client, agent: Mock
    ) -> None:
        async with hold_session(agent, []) as live:
            await asyncio.sleep(0.01)
        assert client.cancelled
        assert live.client.cancelled()

    async def it_kills_the_client_when_the_block_fails(client: Client, agent: Mock) -> None:
        with pytest.raises(ValueError, match="boom"):
            async with hold_session(agent, []) as live:
                await asyncio.sleep(0.01)
                raise ValueError("boom")
        assert client.cancelled
        assert live.client.cancelled()

    async def it_finishes_killing_the_client_through_a_cancel(client: Client, agent: Mock) -> None:
        stopping = asyncio.Event()

        async def hold() -> None:
            async with hold_session(agent, []):
                await asyncio.sleep(0.01)
                stopping.set()

        task = asyncio.ensure_future(hold())
        await stopping.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert client.cancelled

    async def it_swallows_a_client_that_failed_once_the_block_failed(
        client: Client, agent: Mock
    ) -> None:
        client.fails = OSError("no docker")
        with pytest.raises(ValueError, match="boom"):
            async with hold_session(agent, []) as live:
                await asyncio.sleep(0.01)
                raise ValueError("boom")
        assert isinstance(live.client.exception(), OSError)

    async def it_closes_both_ends_of_the_input(agent: Mock) -> None:
        before = open_fds()
        async with hold_session(agent, []) as live:
            live.stdin.close()
            await live.client
        await asyncio.sleep(0.01)
        assert open_fds() <= before

    async def it_closes_both_ends_when_it_cannot_watch_the_input(agent: Mock) -> None:
        before = open_fds()
        loop = asyncio.get_running_loop()
        with (
            patch.object(loop, "connect_write_pipe", side_effect=OSError("no watch")),
            pytest.raises(OSError, match="no watch"),
        ):
            async with hold_session(agent, []):
                pass
        assert open_fds() <= before
