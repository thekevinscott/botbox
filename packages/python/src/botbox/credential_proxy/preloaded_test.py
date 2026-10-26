import os
from pathlib import Path

import pytest

from botbox.credential_proxy.preloaded import preloaded


def open_fds() -> set[str]:
    return {fd.name for fd in Path("/proc/self/fd").iterdir()}


def describe_preloaded() -> None:
    def it_reads_back_the_data_then_eof_as_the_write_end_is_closed() -> None:
        read = preloaded(b"secret")
        try:
            assert os.read(read, 100) == b"secret"
            assert os.read(read, 100) == b""
        finally:
            os.close(read)

    def it_takes_data_past_the_small_int_cache() -> None:
        read = preloaded(b"x" * 1000)
        try:
            assert os.read(read, 2000) == b"x" * 1000
        finally:
            os.close(read)

    def it_refuses_data_bigger_than_the_pipe_and_closes_both_ends() -> None:
        before = open_fds()
        with pytest.raises(BlockingIOError):
            preloaded(b"x" * (16 * 1024 * 1024))
        assert open_fds() == before
