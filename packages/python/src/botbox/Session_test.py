import asyncio
import importlib
import json
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from botbox.Session import Session

# `botbox.Session` the attribute is the class; the limits live on the module.
module = importlib.import_module("botbox.Session")


def lines(*events: Any) -> bytes:
    return "".join((e if isinstance(e, str) else json.dumps(e)) + "\n" for e in events).encode()


class Live:
    """A session over fake pipes: `print` is the CLI writing, `exit` its client exiting."""

    def __init__(self) -> None:
        self.agent = Mock(
            encode=lambda message: f"<{message}>",
            turn_ended=lambda event: event.get("type") == "end",
        )
        self.stdin = Mock(write=Mock(), drain=AsyncMock(), transport=Mock())
        self.stdout = Mock(into=bytearray(), grew=asyncio.Event(), resume=Mock())
        self.stderr = bytearray()
        self.client: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        self.session = Session(self.agent, self.stdin, self.stdout, self.stderr, self.client)

    def print(self, data: bytes) -> None:
        self.stdout.into.extend(data)
        self.stdout.grew.set()

    def exit(self, code: int = 0) -> None:
        self.client.set_result(code)

    @property
    def sent(self) -> bytes:
        return b"".join(c.args[0] for c in self.stdin.write.call_args_list)


class OutputLimitExceeded(Exception):
    pass


@pytest.fixture(autouse=True)
def output_limit_exceeded() -> Iterator[None]:
    with patch("botbox.Session.OutputLimitExceeded", OutputLimitExceeded):
        yield


@pytest.fixture(autouse=True)
def abort_writer() -> Iterator[Mock]:
    with patch("botbox.Session.abort_writer", autospec=True) as m:
        yield m


@pytest.fixture
async def live() -> Live:
    return Live()


async def soon(live: Live, *chunks: bytes) -> None:
    """Print `chunks` one loop pass apart, after the turn has started waiting."""
    for chunk in chunks:
        await asyncio.sleep(0)
        live.print(chunk)


def describe_Session() -> None:
    async def it_keeps_its_agent_and_pipes(live: Live) -> None:
        session = live.session
        assert session.agent is live.agent
        assert session.stdin is live.stdin
        assert session.stdout is live.stdout
        assert session.stderr is live.stderr
        assert session.client is live.client

    async def it_has_no_result_until_the_session_is_left(live: Live) -> None:
        assert live.session.result is None

    async def it_wakes_a_waiting_turn_and_drops_its_input_once_the_client_exits(
        live: Live, abort_writer: Mock
    ) -> None:
        live.exit()
        await asyncio.sleep(0)
        assert live.stdout.grew.is_set()
        abort_writer.assert_called_once_with(live.stdin)

    def describe_stream() -> None:
        async def it_sends_the_encoded_message_on_its_own_line(live: Live) -> None:
            live.print(lines({"type": "end"}))
            [event async for event in live.session.stream("hi")]
            assert live.sent == b"<hi>\n"
            live.stdin.drain.assert_awaited_once_with()

        async def it_yields_events_as_they_arrive_up_to_the_turns_end(live: Live) -> None:
            arriving = asyncio.ensure_future(
                soon(live, lines({"n": 1}), b'{"n"', b': 2}\n{"type": "end"}\n{"n": 3}\n')
            )
            events = [event async for event in live.session.stream("hi")]
            await arriving
            assert events == [{"n": 1}, {"n": 2}, {"type": "end"}]

        async def it_yields_each_event_before_the_next_arrives(live: Live) -> None:
            stream = live.session.stream("hi")
            live.print(lines({"n": 1}))
            assert await anext(stream) == {"n": 1}
            later = asyncio.ensure_future(anext(stream))
            await asyncio.sleep(0.01)
            assert not later.done()
            live.print(lines({"type": "end"}))
            assert await later == {"type": "end"}
            with pytest.raises(StopAsyncIteration):
                await anext(stream)

        async def it_skips_lines_that_are_not_json_objects(live: Live) -> None:
            live.print(lines("starting", "[1, 2]", "\xff", "", {"n": 1}, {"type": "end"}))
            events = [event async for event in live.session.stream("hi")]
            assert events == [{"n": 1}, {"type": "end"}]

        async def it_reads_past_an_empty_first_line(live: Live) -> None:
            live.print(b"\n" + lines({"type": "end"}))
            events = await asyncio.wait_for(live.session.message("hi"), 1)
            assert events == [{"type": "end"}]

        async def it_skips_bytes_that_are_not_utf8(live: Live) -> None:
            live.print(b"\xff\xfe\n" + lines({"type": "end"}))
            events = [event async for event in live.session.stream("hi")]
            assert events == [{"type": "end"}]

        async def it_ends_with_what_arrived_if_the_cli_exits_mid_turn(live: Live) -> None:
            live.print(lines({"n": 1}) + b'{"n": 2')
            live.exit()
            events = [event async for event in live.session.stream("hi")]
            assert events == [{"n": 1}]

        async def it_yields_a_last_line_the_cli_left_unterminated(live: Live) -> None:
            live.print(lines({"n": 1}) + b'{"type": "end"}')
            live.exit()
            assert await live.session.message("hi") == [{"n": 1}, {"type": "end"}]
            assert await live.session.message("again") == []

        async def it_waits_for_the_end_of_a_line_while_the_cli_runs(live: Live) -> None:
            live.print(b'{"type": "end"}')
            later = asyncio.ensure_future(live.session.message("hi"))
            await asyncio.sleep(0.01)
            assert not later.done()
            live.print(b"\n")
            assert await later == [{"type": "end"}]

        async def it_wakes_when_the_cli_exits_while_it_waits(live: Live) -> None:
            stream = live.session.stream("hi")
            later = asyncio.ensure_future(anext(stream))
            await asyncio.sleep(0.01)
            live.exit()
            with pytest.raises(StopAsyncIteration):
                await asyncio.wait_for(later, 1)

        async def it_reads_the_rest_of_the_output_once_the_cli_has_exited(live: Live) -> None:
            live.print(lines({"n": 1}, {"n": 2}, {"type": "end"}))
            live.exit()
            events = [event async for event in live.session.stream("hi")]
            assert events == [{"n": 1}, {"n": 2}, {"type": "end"}]

        @pytest.mark.parametrize("error", [BrokenPipeError, ConnectionResetError])
        async def it_ends_empty_when_the_cli_is_gone_before_the_message(
            live: Live, error: type[Exception]
        ) -> None:
            live.stdin.drain.side_effect = error
            live.exit()
            assert [event async for event in live.session.stream("hi")] == []

        async def it_picks_up_the_next_turn_where_the_last_one_ended(live: Live) -> None:
            live.print(lines({"type": "end"}, {"n": 2}, {"type": "end"}))
            first = [event async for event in live.session.stream("one")]
            second = [event async for event in live.session.stream("two")]
            assert (first, second) == ([{"type": "end"}], [{"n": 2}, {"type": "end"}])

        async def it_skips_the_rest_of_a_turn_left_early_before_sending_the_next(
            live: Live,
        ) -> None:
            live.print(lines({"n": 1}))
            async for _ in live.session.stream("one"):
                break
            assert live.sent == b"<one>\n"
            following = asyncio.ensure_future(live.session.message("two"))
            await asyncio.sleep(0.01)
            assert live.sent == b"<one>\n"
            live.print(lines({"n": 2}, {"type": "end"}, {"n": 3}, {"type": "end"}))
            assert await following == [{"n": 3}, {"type": "end"}]
            assert live.sent == b"<one>\n<two>\n"

        async def it_skips_the_rest_of_a_turn_whose_send_was_cut_short(live: Live) -> None:
            async def drain() -> None:
                if live.stdin.write.call_count == 1:
                    await asyncio.Event().wait()

            live.stdin.drain.side_effect = drain
            sending = asyncio.ensure_future(live.session.message("one"))
            await asyncio.sleep(0.01)
            sending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await sending
            live.print(lines({"n": 1}, {"type": "end"}, {"n": 2}, {"type": "end"}))
            assert await live.session.message("two") == [{"n": 2}, {"type": "end"}]

        async def it_skips_nothing_after_a_turn_left_at_its_end(live: Live) -> None:
            live.print(lines({"type": "end"}, {"n": 2}, {"type": "end"}))
            async for _ in live.session.stream("one"):
                break
            assert await live.session.message("two") == [{"n": 2}, {"type": "end"}]

        async def it_sends_the_next_message_after_a_turn_the_cli_cut_short(live: Live) -> None:
            live.print(lines({"n": 1}))
            live.exit()
            assert await live.session.message("one") == [{"n": 1}]
            assert await live.session.message("two") == []
            assert live.sent == b"<one>\n<two>\n"

    def describe_message() -> None:
        async def it_collects_the_turns_events(live: Live) -> None:
            live.print(lines({"n": 1}, "noise", {"type": "end"}))
            assert await live.session.message("hi") == [{"n": 1}, {"type": "end"}]
            assert live.sent == b"<hi>\n"

    def describe_retention() -> None:
        def it_holds_a_1_gib_line_and_a_1_mib_window() -> None:
            assert (module.LINE_LIMIT, module.WINDOW) == (2**30, 2**20)

        async def it_releases_each_line_once_read(live: Live) -> None:
            def update(n: int) -> dict[str, Any]:
                partial = {"thinking": "x" * 16 * n}
                return {"type": "update", "delta": "x" * 16, "partial": partial, "message": partial}

            count = 400
            longest = len(lines(update(count)))
            held: list[int] = []
            live.print(lines(update(1)))
            async for event in live.session.stream("hi"):
                held.append(len(live.stdout.into))
                if event["type"] == "update":
                    n = len(event["partial"]["thinking"]) // 16
                    live.print(lines(update(n + 1) if n < count else {"type": "end"}))
            assert len(held) == count + 1
            assert max(held) < longest

        async def it_drops_lines_that_are_not_events(live: Live) -> None:
            live.print(lines("starting", {"n": 1}, "[1, 2]", "", {"type": "end"}))
            assert await live.session.message("hi") == [{"n": 1}, {"type": "end"}]
            assert live.stdout.into == b""

        async def it_drains_the_cli_to_its_exit(live: Live) -> None:
            live.print(lines({"n": 1}, "stray"))
            draining = asyncio.ensure_future(live.session.drain())
            await asyncio.sleep(0.01)
            assert not draining.done()
            live.print(lines({"type": "end"}, "last"))
            live.exit()
            await asyncio.wait_for(draining, 1)
            assert live.stdout.into == b""

        async def it_resumes_reading_while_it_waits_for_a_line(live: Live) -> None:
            live.print(b'{"type": ')
            later = asyncio.ensure_future(live.session.message("hi"))
            await asyncio.sleep(0.01)
            live.stdout.resume.assert_called_with()
            live.print(b'"end"}\n')
            assert await later == [{"type": "end"}]

        async def it_ends_the_session_on_a_line_over_the_limit(
            live: Live, monkeypatch: pytest.MonkeyPatch
        ) -> None:
            monkeypatch.setattr(module, "LINE_LIMIT", 10)
            live.print(lines({"n": 1}) + b"x" * 11)
            stream = live.session.stream("hi")
            assert await anext(stream) == {"n": 1}
            with pytest.raises(OutputLimitExceeded, match="10 bytes"):
                await anext(stream)
            assert live.client.cancelled()
            assert live.stdout.into == b""
            with pytest.raises(OutputLimitExceeded):
                await live.session.message("again")
            with pytest.raises(OutputLimitExceeded):
                await live.session.drain()

        async def it_reads_a_line_at_the_limit(live: Live, monkeypatch: pytest.MonkeyPatch) -> None:
            monkeypatch.setattr(module, "LINE_LIMIT", 15)
            live.print(b'{"type": "end"}')
            later = asyncio.ensure_future(live.session.message("hi"))
            await asyncio.sleep(0.01)
            assert not later.done()
            live.print(b"\n")
            assert await later == [{"type": "end"}]
