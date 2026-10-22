import fcntl
import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from botbox.Claim import Claim
from botbox.close_held import HELD

TOKEN = "0123456789ab"


@pytest.fixture(autouse=True)
def runs(tmp_path: Path) -> Iterator[Path]:
    with patch("botbox.Claim.run_dir", return_value=tmp_path):
        yield tmp_path


def locked(lock: Path) -> bool:
    """Whether another open of `lock` finds it held, as a sweep would."""
    fd = os.open(lock, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    finally:
        os.close(fd)
    return False


def describe_claim() -> None:
    def it_makes_an_owner_only_dir_named_for_the_token(runs: Path) -> None:
        claim = Claim(TOKEN)
        assert claim.path == runs / TOKEN
        assert claim.path.stat().st_mode & 0o777 == 0o700
        claim.cleanup()

    def it_holds_the_lock_beside_it_for_as_long_as_it_lives(runs: Path) -> None:
        claim = Claim(TOKEN)
        assert sorted(p.name for p in runs.iterdir()) == [TOKEN, f"{TOKEN}.lock"]
        assert locked(runs / f"{TOKEN}.lock")
        claim.cleanup()

    def it_locks_before_the_lock_file_has_its_name() -> None:
        seen: list[bool] = []
        hardlink_to = Path.hardlink_to

        def check(self: Path, target: Path) -> None:
            seen.append(locked(target))
            hardlink_to(self, target)

        with patch.object(Path, "hardlink_to", check):
            Claim(TOKEN).cleanup()
        assert seen == [True]

    def it_removes_the_dir_then_the_lock_and_lets_go(runs: Path) -> None:
        claim = Claim(TOKEN)
        (claim.path / "home").mkdir()
        claim.cleanup()
        assert list(runs.iterdir()) == []

    def it_keeps_the_lock_file_for_a_sweep_when_the_dir_will_not_go(runs: Path) -> None:
        claim = Claim(TOKEN)
        with (
            patch("botbox.Claim.remove_tree", side_effect=PermissionError("agent's")),
            pytest.raises(PermissionError),
        ):
            claim.cleanup()
        assert (runs / f"{TOKEN}.lock").exists()
        assert not locked(runs / f"{TOKEN}.lock")

    def it_refuses_a_token_already_claimed() -> None:
        claim = Claim(TOKEN)
        with pytest.raises(FileExistsError):
            Claim(TOKEN)
        claim.cleanup()

    def it_lets_go_when_it_cannot_make_the_dir(runs: Path) -> None:
        (runs / TOKEN).mkdir()
        with pytest.raises(FileExistsError):
            Claim(TOKEN)
        assert not locked(runs / f"{TOKEN}.lock")

    def it_is_closed_in_forked_children_until_it_lets_go() -> None:
        claim = Claim(TOKEN)
        assert claim._held in HELD  # noqa: SLF001
        claim.cleanup()
        assert claim._held not in HELD  # noqa: SLF001
        assert claim._held.closed  # noqa: SLF001
