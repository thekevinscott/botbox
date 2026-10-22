import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from botbox.run_dir import run_dir


@pytest.fixture(autouse=True)
def temp(tmp_path: Path) -> Iterator[Path]:
    with patch.object(tempfile, "tempdir", str(tmp_path)):
        yield tmp_path


def describe_run_dir() -> None:
    def it_is_named_for_the_user_in_the_system_temp_dir(temp: Path) -> None:
        assert run_dir() == temp / f"botbox-{os.getuid()}"

    def it_makes_it_owner_only() -> None:
        assert run_dir().stat().st_mode & 0o777 == 0o700

    def it_reuses_one_that_exists() -> None:
        (run_dir() / "kept").touch()
        assert (run_dir() / "kept").exists()

    @pytest.mark.parametrize("mode", [0o755, 0o701, 0o720])
    def it_refuses_one_others_can_open(temp: Path, mode: int) -> None:
        (temp / f"botbox-{os.getuid()}").mkdir()
        (temp / f"botbox-{os.getuid()}").chmod(mode)
        with pytest.raises(PermissionError, match="only you can open"):
            run_dir()

    def it_refuses_a_symlink(temp: Path) -> None:
        elsewhere = temp / "elsewhere"
        elsewhere.mkdir(mode=0o700)
        (temp / f"botbox-{os.getuid()}").symlink_to(elsewhere)
        with pytest.raises(PermissionError):
            run_dir()

    @pytest.mark.parametrize("offset", [1, -1])
    def it_refuses_one_another_user_owns(temp: Path, offset: int) -> None:
        other = os.getuid() + offset
        (temp / f"botbox-{other}").mkdir(mode=0o700)
        with (
            patch("botbox.run_dir.os.getuid", return_value=other),
            pytest.raises(PermissionError),
        ):
            run_dir()
