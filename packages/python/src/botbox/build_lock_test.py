from collections.abc import Callable, Iterator
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

import pytest

from botbox.build_lock import build_lock

WAIT = 0.2


@pytest.fixture(autouse=True)
def lock_dir(tmp_path: Path) -> Iterator[Path]:
    with patch("botbox.build_lock.build_lock_path", lambda tag: tmp_path / f"{tag}.lock"):
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

    def it_locks_the_file_build_lock_path_names(lock_dir: Path) -> None:
        with build_lock("an-agent:latest"):
            assert (lock_dir / "an-agent:latest.lock").exists()
