import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from adocker.Capture import Capture


def open_fds() -> set[str]:
    return {fd.name for fd in Path("/proc/self/fd").iterdir()}


def describe_Capture() -> None:
    async def it_collects_what_is_written_to_its_pipe() -> None:
        into = bytearray(b"kept ")
        async with Capture(into) as capture:
            os.write(capture.write, b"everything")
            capture.release()
            await capture.eof
        assert into == b"kept everything"

    async def it_keeps_only_the_last_limit_bytes() -> None:
        into = bytearray()
        async with Capture(into, 3) as capture:
            os.write(capture.write, b"a" * 100)
            os.write(capture.write, b"bc")
            capture.release()
            await capture.eof
        assert into == b"abc"

    async def it_keeps_everything_under_the_limit() -> None:
        into = bytearray()
        async with Capture(into, 10) as capture:
            os.write(capture.write, b"shorter")
            capture.release()
            await capture.eof
        assert into == b"shorter"

    async def it_signals_each_arrival() -> None:
        into = bytearray()
        async with Capture(into) as capture:
            assert not capture.grew.is_set()
            os.write(capture.write, b"line\n")
            await asyncio.wait_for(capture.grew.wait(), 1)
            assert into == b"line\n"
            capture.grew.clear()
            os.write(capture.write, b"more")
            await asyncio.wait_for(capture.grew.wait(), 1)
            capture.release()
            await capture.eof
        assert into == b"line\nmore"

    async def it_releases_its_write_end_once() -> None:
        async with Capture(bytearray()) as capture:
            capture.release()
            capture.release()
            await capture.eof

    async def it_keeps_what_it_read_from_a_pipe_still_open_elsewhere() -> None:
        into = bytearray()
        async with Capture(into) as capture:
            held = os.dup(capture.write)
            capture.release()
            os.write(held, b"partial")
            await asyncio.sleep(0.01)
        await asyncio.wait_for(capture.eof, 1)
        assert into == b"partial"
        with pytest.raises(BrokenPipeError):
            os.write(held, b"more")
        os.close(held)

    async def it_closes_both_ends_on_exit() -> None:
        before = open_fds()
        async with Capture(bytearray()):
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
            async with Capture(bytearray()):
                pass
        assert open_fds() <= before
