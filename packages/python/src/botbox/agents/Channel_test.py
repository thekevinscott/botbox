import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from botbox.agents.Channel import Channel


def everything(_message: object) -> bool:
    return True


def message(kind: str) -> Mock:
    return Mock(type=kind)


async def drain(subscription: object) -> list[object]:
    return [item async for item in subscription]  # type: ignore[attr-defined]


def describe_channel() -> None:
    def describe_send() -> None:
        async def it_writes_the_line_and_drains() -> None:
            channel = Channel()
            channel.stdin = Mock(drain=AsyncMock())
            await channel.send(b"hi\n")
            channel.stdin.write.assert_called_once_with(b"hi\n")
            channel.stdin.drain.assert_awaited_once_with()

        async def it_refuses_before_the_cli_starts() -> None:
            with pytest.raises(RuntimeError, match="not started"):
                await Channel().send(b"hi\n")

    def describe_subscriptions() -> None:
        async def it_yields_what_it_wants_from_when_it_opened_until_the_end() -> None:
            channel = Channel()
            channel.publish(message("early"))
            subscription = channel.subscribe(lambda m: m.type != "skip")
            late, skip = message("late"), message("skip")
            channel.publish(late)
            channel.publish(skip)
            channel.end()
            assert await drain(subscription) == [late]

        async def it_hands_every_subscription_each_message() -> None:
            channel = Channel()
            first, second = channel.subscribe(everything), channel.subscribe(everything)
            one = message("one")
            channel.publish(one)
            channel.end()
            assert await drain(first) == await drain(second) == [one]

        async def it_waits_for_the_next_message() -> None:
            channel = Channel()
            subscription = channel.subscribe(everything)
            waiting = asyncio.ensure_future(anext(subscription))
            await asyncio.sleep(0)
            assert not waiting.done()
            one = message("one")
            channel.publish(one)
            assert await waiting is one

        async def it_stays_ended() -> None:
            channel = Channel()
            subscription = channel.subscribe(everything)
            channel.end()
            assert await drain(subscription) == []
            assert await drain(subscription) == []

        async def it_ends_at_once_when_opened_after_the_end() -> None:
            channel = Channel()
            channel.end()
            assert await drain(channel.subscribe(everything)) == []

    def describe_callbacks() -> None:
        def it_calls_each_with_what_it_wants() -> None:
            channel = Channel()
            heard, all_ = Mock(), Mock()
            channel.listen(lambda m: m.type == "reply", heard)
            channel.listen(everything, all_)
            reply, tool = message("reply"), message("tool")
            channel.publish(reply)
            channel.publish(tool)
            assert [c.args[0] for c in heard.call_args_list] == [reply]
            assert [c.args[0] for c in all_.call_args_list] == [reply, tool]

        def it_lets_a_callback_error_out_of_publish() -> None:
            channel = Channel()
            channel.listen(everything, Mock(side_effect=ValueError("boom")))
            with pytest.raises(ValueError, match="boom"):
                channel.publish(message("one"))
