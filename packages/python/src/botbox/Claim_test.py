import asyncio
import os
import sys
from collections.abc import Iterator
from io import BufferedWriter
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from botbox.Claim import Claim

TOKEN = "0123456789ab"


@pytest.fixture(autouse=True)
def runs(tmp_path: Path) -> Iterator[Path]:
    with patch("botbox.Claim.run_dir", return_value=tmp_path):
        yield tmp_path


@pytest.fixture(autouse=True)
def fcntl() -> Iterator[MagicMock]:
    with patch("botbox.Claim.fcntl") as m:
        yield m


@pytest.fixture(autouse=True)
def held() -> Iterator[set[BufferedWriter]]:
    held: set[BufferedWriter] = set()
    with patch("botbox.Claim.HELD", held):
        yield held


def describe_claim() -> None:
    def it_makes_an_owner_only_dir_named_for_the_token(runs: Path) -> None:
        claim = Claim(TOKEN)
        assert claim.path == runs / TOKEN
        assert claim.path.stat().st_mode & 0o777 == 0o700
        claim.cleanup()

    def it_locks_the_lock_file_beside_it_without_blocking(runs: Path, fcntl: MagicMock) -> None:
        claim = Claim(TOKEN)
        assert sorted(p.name for p in runs.iterdir()) == [TOKEN, f"{TOKEN}.lock"]
        [(lock, flags)] = [c.args for c in fcntl.flock.call_args_list]
        assert flags == fcntl.LOCK_EX | fcntl.LOCK_NB
        assert os.fstat(lock.fileno()).st_ino == (runs / f"{TOKEN}.lock").stat().st_ino
        assert not lock.closed
        claim.cleanup()

    def it_locks_before_the_lock_file_has_its_name(fcntl: MagicMock) -> None:
        seen: list[int] = []
        hardlink_to = Path.hardlink_to

        def check(self: Path, target: Path) -> None:
            seen.append(fcntl.flock.call_count)
            hardlink_to(self, target)

        with patch.object(Path, "hardlink_to", check):
            Claim(TOKEN).cleanup()
        assert seen == [1]

    def it_is_closed_in_forked_children_until_it_lets_go(held: set[BufferedWriter]) -> None:
        claim = Claim(TOKEN)
        [lock] = held
        claim.cleanup()
        assert held == set()
        assert lock.closed

    def it_removes_the_dir_then_the_lock_and_lets_go(runs: Path, fcntl: MagicMock) -> None:
        claim = Claim(TOKEN)
        (claim.path / "home").mkdir()
        claim.cleanup()
        assert list(runs.iterdir()) == []
        assert fcntl.flock.call_args.args[0].closed

    def it_keeps_the_lock_file_for_a_sweep_when_the_dir_will_not_go(
        runs: Path, fcntl: MagicMock, held: set[BufferedWriter]
    ) -> None:
        claim = Claim(TOKEN)
        with (
            patch("botbox.Claim.remove_tree", side_effect=PermissionError("agent's")),
            pytest.raises(PermissionError),
        ):
            claim.cleanup()
        assert (runs / f"{TOKEN}.lock").exists()
        assert fcntl.flock.call_args.args[0].closed
        assert held == set()

    def it_refuses_a_lock_file_left_half_made(runs: Path) -> None:
        (runs / f".{TOKEN}.pending").touch()
        with pytest.raises(FileExistsError):
            Claim(TOKEN)

    def it_refuses_a_token_already_claimed(runs: Path) -> None:
        claim = Claim(TOKEN)
        with pytest.raises(FileExistsError):
            Claim(TOKEN)
        assert sorted(p.name for p in runs.iterdir()) == [TOKEN, f"{TOKEN}.lock"]
        claim.cleanup()

    def it_lets_go_when_it_cannot_make_the_dir(
        runs: Path, fcntl: MagicMock, held: set[BufferedWriter]
    ) -> None:
        (runs / TOKEN).mkdir()
        with pytest.raises(FileExistsError):
            Claim(TOKEN)
        assert fcntl.flock.call_args.args[0].closed
        assert held == set()


def describe_process_imports() -> None:
    async def it_uses_the_relocated_helpers() -> None:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "from botbox.Claim import HELD; "
            "from botbox.posix_tools.process.close_held import HELD as shared; "
            "assert HELD is shared; ",
        )
        assert await process.wait() == 0
