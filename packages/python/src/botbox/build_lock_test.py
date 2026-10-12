from collections.abc import Callable, Iterator
from fnmatch import fnmatch
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

import pytest

from botbox.build_lock import build_lock

WAIT = 0.2


@pytest.fixture(autouse=True)
def tempdir(tmp_path: Path) -> Iterator[Path]:
    with patch("botbox.build_lock.gettempdir", return_value=str(tmp_path)):
        yield tmp_path


def holding(tag: str, held: Event, release: Event) -> Callable[[], None]:
    def hold() -> None:
        with build_lock(tag):
            held.set()
            release.wait()

    return hold


def acquires(tag: str) -> Event:
    acquired = Event()

    def take() -> None:
        with build_lock(tag):
            acquired.set()

    Thread(target=take, daemon=True).start()
    return acquired


def describe_build_lock() -> None:
    def it_blocks_a_second_holder_of_the_same_tag_until_released() -> None:
        held, release = Event(), Event()
        Thread(target=holding("an-agent:latest", held, release), daemon=True).start()
        assert held.wait(WAIT * 10)
        acquired = acquires("an-agent:latest")
        assert not acquired.wait(WAIT)
        release.set()
        assert acquired.wait(WAIT * 10)

    def it_does_not_block_a_different_tag() -> None:
        held, release = Event(), Event()
        Thread(target=holding("an-agent:latest", held, release), daemon=True).start()
        assert held.wait(WAIT * 10)
        assert acquires("another-agent:latest").wait(WAIT * 10)
        release.set()

    def it_keeps_its_lock_file_in_the_temp_dir(tempdir: Path) -> None:
        with build_lock("an-agent:latest"):
            pass
        [path] = tempdir.iterdir()
        assert fnmatch(path.name, "botbox-build-*.lock")
