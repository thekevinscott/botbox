import asyncio
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

from botbox.hold_session import hold_session


def read(line: bytes) -> object:
    """A line holding a word as a message: the word; anything else, none."""
    word = line.strip()
    return word.decode() if word.isalpha() else None


class Image:
    """Image.run: an attached client whose CLI echoes each line it reads."""

    def __init__(self) -> None:
        self.tag = ""
        self.command: tuple[str, ...] = ()
        self.options: dict[str, Any] = {}
        self.cancelled = False
        self.fails: BaseException | None = None
        self.refuses: BaseException | None = None

    def __call__(self, tag: str) -> "Image":
        self.tag = tag
        return self

    async def run(self, *command: str, **options: Any) -> Mock:
        self.command, self.options = command, options
        if self.refuses is not None:
            raise self.refuses
        assert options["stdin"] == asyncio.subprocess.PIPE
        loop = asyncio.get_running_loop()
        read, write = os.pipe()
        transport, protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, os.fdopen(write, "wb")
        )
        stdin = asyncio.StreamWriter(transport, protocol, None, loop)
        client = asyncio.ensure_future(self.attached(read, options["stdout"], options["stderr"]))
        return Mock(client=client, stdin=stdin)

    async def attached(self, read: int, out: Any, err: Any) -> int:
        reader = asyncio.StreamReader()
        transport, _ = await asyncio.get_running_loop().connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(reader), os.fdopen(read, "rb")
        )
        try:
            if self.fails is not None:
                raise self.fails
            while line := await reader.readline():
                out(line)
            err(b"bye\n")
            return 7
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        finally:
            transport.close()


@pytest.fixture(autouse=True)
def image() -> Iterator[Image]:
    fake = Image()
    with patch("botbox.hold_session.Image", fake):
        yield fake


@pytest.fixture(autouse=True)
def abort_writer() -> Iterator[Mock]:
    def abort(writer: asyncio.StreamWriter) -> None:
        if not writer.transport.is_closing():
            writer.transport.abort()

    with patch("botbox.hold_session.abort_writer", autospec=True, side_effect=abort) as m:
        yield m


@pytest.fixture
def agent() -> Mock:
    return Mock(read_message=Mock(side_effect=read))


@pytest.fixture
def channel() -> Mock:
    return Mock(stdin=None)


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    path = tmp_path / "scratch"
    path.mkdir()
    return path


def hold(
    agent: Mock, channel: Mock, scratch: Path, output: Path | None = None, home: bytes = b""
) -> Any:
    return hold_session(
        agent,
        channel,
        "img",
        ["cli"],
        home=home,
        scratch=scratch,
        output=output,
        name="c",
        init=True,
    )


async def finish(container: Mock) -> int:
    container.stdin.close()
    return int(await container.client)


def published(channel: Mock) -> list[object]:
    return [call.args[0] for call in channel.publish.call_args_list]


def describe_hold_session() -> None:
    async def it_runs_the_command_on_the_image_with_its_options(
        image: Image, agent: Mock, channel: Mock, scratch: Path
    ) -> None:
        async with hold(agent, channel, scratch) as container:
            assert (image.tag, image.command) == ("img", ("cli",))
            assert (image.options["name"], image.options["init"]) == ("c", True)
            assert channel.stdin is container.stdin

    async def it_writes_each_line_then_publishes_what_the_agent_reads_from_it(
        agent: Mock, channel: Mock, scratch: Path
    ) -> None:
        async with hold(agent, channel, scratch) as container:
            container.stdin.write(b"one\n{not a word}\ntwo\n")
            assert await finish(container) == 7
        assert (scratch / "stdout.txt").read_bytes() == b"one\n{not a word}\ntwo\n"
        assert (scratch / "stderr.txt").read_bytes() == b"bye\n"
        assert [call.args[0] for call in agent.read_message.call_args_list] == [
            b"one\n",
            b"{not a word}\n",
            b"two\n",
        ]
        assert published(channel) == ["one", "two"]

    async def it_writes_a_line_before_it_is_published(
        agent: Mock, channel: Mock, scratch: Path
    ) -> None:
        seen: list[bytes] = []
        channel.publish.side_effect = lambda _: seen.append((scratch / "stdout.txt").read_bytes())
        async with hold(agent, channel, scratch) as container:
            container.stdin.write(b"one\n")
            await finish(container)
        assert seen == [b"one\n"]

    async def it_sends_the_home_ahead_of_the_first_message(
        agent: Mock, channel: Mock, scratch: Path
    ) -> None:
        async with hold(agent, channel, scratch, home=b"home\n") as container:
            container.stdin.write(b"one\n")
            await finish(container)
        assert (scratch / "stdout.txt").read_bytes() == b"home\none\n"
        assert published(channel) == ["home", "one"]

    async def it_copies_the_output_to_the_output_folder(
        agent: Mock, channel: Mock, scratch: Path, tmp_path: Path
    ) -> None:
        (tmp_path / "stdout.txt").write_text("old")
        async with hold(agent, channel, scratch, tmp_path) as container:
            container.stdin.write(b"one\n")
            await finish(container)
        assert (tmp_path / "stdout.txt").read_bytes() == b"one\n"
        assert (tmp_path / "stderr.txt").read_bytes() == b"bye\n"

    async def it_publishes_a_final_unterminated_line_then_ends_the_channel(
        agent: Mock, channel: Mock, scratch: Path
    ) -> None:
        order: list[object] = []
        channel.publish.side_effect = order.append
        channel.end.side_effect = lambda: order.append("end")
        async with hold(agent, channel, scratch) as container:
            container.stdin.write(b"last")
            await finish(container)
            assert order == ["last", "end"]

    async def it_ends_the_channel_even_if_publishing_the_rest_fails(
        agent: Mock, channel: Mock, scratch: Path
    ) -> None:
        channel.publish.side_effect = ValueError("callback")
        async with hold(agent, channel, scratch) as container:
            container.stdin.write(b"last")
            await finish(container)
            channel.end.assert_called_once_with()

    async def it_aborts_the_input_once_the_client_exits(
        agent: Mock, channel: Mock, scratch: Path, abort_writer: Mock
    ) -> None:
        async with hold(agent, channel, scratch) as container:
            await finish(container)
            abort_writer.assert_called_once_with(container.stdin)

    async def it_kills_the_client_if_it_is_still_running_on_leaving(
        image: Image, agent: Mock, channel: Mock, scratch: Path
    ) -> None:
        async with hold(agent, channel, scratch) as container:
            await asyncio.sleep(0.01)
        assert image.cancelled
        assert container.client.cancelled()

    async def it_kills_the_client_when_the_block_fails(
        image: Image, agent: Mock, channel: Mock, scratch: Path
    ) -> None:
        with pytest.raises(ValueError, match="boom"):
            async with hold(agent, channel, scratch):
                await asyncio.sleep(0.01)
                raise ValueError("boom")
        assert image.cancelled

    async def it_finishes_killing_the_client_through_a_cancel(
        image: Image, agent: Mock, channel: Mock, scratch: Path
    ) -> None:
        stopping = asyncio.Event()

        async def held() -> None:
            async with hold(agent, channel, scratch):
                await asyncio.sleep(0.01)
                stopping.set()

        task = asyncio.ensure_future(held())
        await stopping.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert image.cancelled

    async def it_swallows_a_client_that_failed_once_the_block_failed(
        image: Image, agent: Mock, channel: Mock, scratch: Path
    ) -> None:
        image.fails = OSError("no docker")
        with pytest.raises(ValueError, match="boom"):
            async with hold(agent, channel, scratch) as container:
                await asyncio.sleep(0.01)
                raise ValueError("boom")
        assert isinstance(container.client.exception(), OSError)

    async def it_aborts_the_input_once_left(
        agent: Mock, channel: Mock, scratch: Path, abort_writer: Mock
    ) -> None:
        async with hold(agent, channel, scratch) as container:
            abort_writer.assert_not_called()
        abort_writer.assert_called_with(container.stdin)

    async def it_raises_when_the_run_will_not_start(
        image: Image, agent: Mock, channel: Mock, scratch: Path
    ) -> None:
        image.refuses = OSError("no docker")
        with pytest.raises(OSError, match="no docker"):
            async with hold(agent, channel, scratch):
                pytest.fail("yielded")

    def it_takes_home_scratch_and_output_by_keyword_only(
        agent: Mock, channel: Mock, scratch: Path
    ) -> None:
        with pytest.raises(TypeError):
            hold_session(agent, channel, "img", ["cli"], b"", scratch, None)  # type: ignore[call-arg]
