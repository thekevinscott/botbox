from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from botbox.reap import reap

DEAD, LIVE = "0123456789ab", "ba9876543210"


@pytest.fixture(autouse=True)
def runs(tmp_path: Path) -> Iterator[Path]:
    with patch("botbox.reap.run_dir", return_value=tmp_path):
        yield tmp_path


@pytest.fixture(autouse=True)
def reap_run() -> Iterator[AsyncMock]:
    async def dead(lock: Path) -> bool:
        return lock.stem == DEAD

    with patch("botbox.reap.reap_run", autospec=True, side_effect=dead) as m:
        yield m


def describe_reap() -> None:
    async def it_sweeps_each_runs_lock_and_returns_the_tokens_it_reaped(
        runs: Path, reap_run: AsyncMock
    ) -> None:
        for token in (DEAD, LIVE):
            (runs / f"{token}.lock").touch()
            (runs / token).mkdir()
        assert await reap() == [DEAD]
        assert sorted(c.args[0] for c in reap_run.await_args_list) == [
            runs / f"{DEAD}.lock",
            runs / f"{LIVE}.lock",
        ]

    @pytest.mark.parametrize("name", [f".{DEAD}.pending", "notatoken.lock", "build.lock"])
    async def it_ignores_anything_not_a_runs_lock(
        runs: Path, reap_run: AsyncMock, name: str
    ) -> None:
        (runs / name).touch()
        assert await reap() == []
        reap_run.assert_not_awaited()
