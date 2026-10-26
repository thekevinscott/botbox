import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from botbox.hold_session import hold_session


def open_fds() -> set[str]:
    return {fd.name for fd in Path("/proc/self/fd").iterdir()}


class Client:
    """The attached `docker run`: what it was given, and a CLI that echoes each line it reads.

    Each line it prints also goes to `printed`, which the fake `tail` follows.
    """

    def __init__(self) -> None:
        self.args: list[str] = []
        self.options: dict[str, Any] = {}
        self.cancelled = False
        self.fails: BaseException | None = None
        self.printed: asyncio.Queue[bytes] = asyncio.Queue()

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
                os.write(out.fileno(), line)
                self.printed.put_nowait(line)
            os.write(err.fileno(), b"bye\n")
            return 7
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        finally:
            transport.close()


@pytest.fixture(autouse=True)
def client() -> Iterator[Client]:
    client = Client()
    with patch("botbox.hold_session.execute", client):
        yield client


@pytest.fixture(autouse=True)
def followed(client: Client) -> Iterator[list[tuple[Path, int | None, bool]]]:
    calls: list[tuple[Path, int | None, bool]] = []

    @asynccontextmanager
    async def tail(path: Path, *, n: int | None, follow: bool) -> AsyncIterator[Any]:
        calls.append((path, n, follow))

        async def lines() -> AsyncIterator[bytes]:
            while True:
                yield await client.printed.get()

        yield lines()

    with patch("botbox.hold_session.tail", tail):
        yield calls


@pytest.fixture
def output(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture(autouse=True)
def owner_only() -> Iterator[MagicMock]:
    with patch("botbox.hold_session.owner_only", autospec=True) as m:
        yield m


@pytest.fixture(autouse=True)
def abort_writer() -> Iterator[Mock]:
    def abort(writer: asyncio.StreamWriter) -> None:
        if not writer.transport.is_closing():
            writer.transport.abort()

    with patch("botbox.hold_session.abort_writer", autospec=True, side_effect=abort) as m:
        yield m


@pytest.fixture
def agent() -> Mock:
    return Mock(encode=lambda message: message, turn_ended=lambda event: event == {"type": "end"})


def describe_hold_session() -> None:
    async def it_starts_the_attached_run_with_its_args(
        client: Client, agent: Mock, output: Path
    ) -> None:
        async with hold_session(agent, ["--interactive", "img"], output) as live:
            await asyncio.sleep(0.01)
            assert client.args == ["run", "--interactive", "img"]
            assert live.agent is agent
            live.stdin.close()
            await live.client

    async def it_yields_a_session_on_the_agent(agent: Mock, output: Path) -> None:
        with patch("botbox.hold_session.Session") as session:
            async with hold_session(agent, [], output) as live:
                assert live is session.return_value
        assert session.call_args.args[0] is agent

    async def it_streams_the_clis_output_back_to_the_session(agent: Mock, output: Path) -> None:
        async with hold_session(agent, [], output) as live:
            assert await live.message('{"type": "end"}') == [{"type": "end"}]
            live.stdin.close()
            assert await live.client == 7
        assert (output / "stdout.txt").read_bytes() == b'{"type": "end"}\n'
        assert (output / "stderr.txt").read_bytes() == b"bye\n"

    async def it_holds_the_input_for_this_process_alone(
        agent: Mock, owner_only: MagicMock, output: Path
    ) -> None:
        async with hold_session(agent, [], output) as live:
            owner_only.assert_called_once_with(live.stdin.transport.get_extra_info("pipe"))
            owner_only.return_value.__exit__.assert_not_called()
        owner_only.return_value.__exit__.assert_called_once()

    async def it_kills_the_client_if_it_is_still_running_on_leaving(
        client: Client, agent: Mock, output: Path
    ) -> None:
        async with hold_session(agent, [], output) as live:
            await asyncio.sleep(0.01)
        assert client.cancelled
        assert live.client.cancelled()

    async def it_kills_the_client_when_the_block_fails(
        client: Client, agent: Mock, output: Path
    ) -> None:
        with pytest.raises(ValueError, match="boom"):
            async with hold_session(agent, [], output) as live:
                await asyncio.sleep(0.01)
                raise ValueError("boom")
        assert client.cancelled
        assert live.client.cancelled()

    async def it_finishes_killing_the_client_through_a_cancel(
        client: Client, agent: Mock, output: Path
    ) -> None:
        stopping = asyncio.Event()

        async def hold() -> None:
            async with hold_session(agent, [], output):
                await asyncio.sleep(0.01)
                stopping.set()

        task = asyncio.ensure_future(hold())
        await stopping.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert client.cancelled

    async def it_swallows_a_client_that_failed_once_the_block_failed(
        client: Client, agent: Mock, output: Path
    ) -> None:
        client.fails = OSError("no docker")
        with pytest.raises(ValueError, match="boom"):
            async with hold_session(agent, [], output) as live:
                await asyncio.sleep(0.01)
                raise ValueError("boom")
        assert isinstance(live.client.exception(), OSError)

    async def it_aborts_the_input_once_left(agent: Mock, abort_writer: Mock, output: Path) -> None:
        async with hold_session(agent, [], output) as live:
            abort_writer.assert_not_called()
        abort_writer.assert_called_once_with(live.stdin)

    async def it_aborts_the_input_when_its_output_cannot_be_opened(
        agent: Mock, abort_writer: Mock, tmp_path: Path
    ) -> None:
        with pytest.raises(FileNotFoundError):
            async with hold_session(agent, [], tmp_path / "missing"):
                pass
        [(writer,)] = [c.args for c in abort_writer.call_args_list]
        assert writer.transport.is_closing()

    async def it_closes_both_ends_of_the_input(agent: Mock, output: Path) -> None:
        before = open_fds()
        async with hold_session(agent, [], output) as live:
            live.stdin.close()
            await live.client
        await asyncio.sleep(0.01)
        assert open_fds() <= before

    async def it_closes_both_ends_when_it_cannot_watch_the_input(agent: Mock, output: Path) -> None:
        before = open_fds()
        loop = asyncio.get_running_loop()
        with (
            patch.object(loop, "connect_write_pipe", side_effect=OSError("no watch")),
            pytest.raises(OSError, match="no watch"),
        ):
            async with hold_session(agent, [], output):
                pass
        assert open_fds() <= before


def describe_its_output() -> None:
    @pytest.fixture
    def files_client() -> Iterator[Mock]:
        async def attached(_args: list[str], **options: Any) -> int:
            os.write(options["stdout"].fileno(), b"out\n")
            os.write(options["stderr"].fileno(), b"err\n")
            await asyncio.Event().wait()
            return 0

        with patch("botbox.hold_session.execute", side_effect=attached) as m:
            yield m

    async def it_hands_the_client_files_and_follows_stdout(
        agent: Mock,
        files_client: Mock,
        followed: list[tuple[Path, int | None, bool]],
        output: Path,
    ) -> None:
        (output / "stdout.txt").write_text("old")
        async with hold_session(agent, ["img"], output) as live:
            await asyncio.sleep(0.01)
        options = files_client.call_args.kwargs
        assert files_client.call_args.args == (["run", "img"],)
        assert options["stdout"].name == str(output / "stdout.txt")
        assert options["stderr"].name == str(output / "stderr.txt")
        assert options["stdout"].closed
        assert options["stderr"].closed
        assert followed == [(output / "stdout.txt", None, True)]
        assert (output / "stdout.txt").read_bytes() == b"out\n"
        assert (output / "stderr.txt").read_bytes() == b"err\n"
        assert live.client.cancelled()
