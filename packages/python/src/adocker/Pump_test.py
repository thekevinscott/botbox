import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from adocker.Pump import Pump


def open_fds() -> set[str]:
    return {fd.name for fd in Path("/proc/self/fd").iterdir()}


def describe_Pump() -> None:
    async def it_hands_each_chunk_to_its_sink() -> None:
        chunks: list[bytes] = []
        async with Pump(chunks.append) as pump:
            os.write(pump.write, b"first")
            await asyncio.sleep(0.01)
            os.write(pump.write, b"second")
            pump.release()
            await pump.eof
        assert chunks == [b"first", b"second"]

    async def it_raises_what_the_sink_raised_and_stops_reading() -> None:
        chunks: list[bytes] = []

        def sink(chunk: bytes) -> None:
            chunks.append(chunk)
            raise OSError("disk full")

        async with Pump(sink) as pump:
            os.write(pump.write, b"one")
            with pytest.raises(OSError, match="disk full"):
                await asyncio.wait_for(asyncio.shield(pump.eof), 1)
            await asyncio.sleep(0.01)
            with pytest.raises(BrokenPipeError):
                os.write(pump.write, b"two")
        assert chunks == [b"one"]

    async def it_releases_its_write_end_once() -> None:
        async with Pump(lambda _: None) as pump:
            pump.release()
            pump.release()
            await pump.eof

    async def it_hands_over_what_arrives_from_a_pipe_still_open_elsewhere() -> None:
        chunks: list[bytes] = []
        async with Pump(chunks.append) as pump:
            held = os.dup(pump.write)
            pump.release()
            os.write(held, b"partial")
            await asyncio.sleep(0.01)
        await asyncio.wait_for(pump.eof, 1)
        assert chunks == [b"partial"]
        with pytest.raises(BrokenPipeError):
            os.write(held, b"more")
        os.close(held)

    async def it_closes_both_ends_on_exit() -> None:
        before = open_fds()
        async with Pump(lambda _: None):
            pass
        await asyncio.sleep(0.01)
        assert open_fds() <= before

    async def it_closes_both_ends_when_it_cannot_watch_the_pipe() -> None:
        before = open_fds()
        loop = asyncio.get_running_loop()
        with (
            patch.object(loop, "connect_read_pipe", side_effect=OSError("no watch")),
            pytest.raises(OSError, match="no watch"),
        ):
            async with Pump(lambda _: None):
                pass
        assert open_fds() <= before
