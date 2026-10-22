import os
from pathlib import Path

import pytest

from botbox.open_dir import open_dir


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "root" / "a" / "b").mkdir(parents=True)
    return tmp_path / "root"


def describe_open_dir() -> None:
    def it_opens_the_dir_below_root(root: Path) -> None:
        fd = open_dir(root, ("a", "b"))
        try:
            assert Path(f"/proc/self/fd/{fd}").samefile(root / "a" / "b")
        finally:
            os.close(fd)

    def it_opens_root_itself_with_no_parts(root: Path) -> None:
        fd = open_dir(root, ())
        try:
            assert Path(f"/proc/self/fd/{fd}").samefile(root)
        finally:
            os.close(fd)

    def it_refuses_a_link_on_the_way(root: Path) -> None:
        (root / "link").symlink_to(root / "a")
        with pytest.raises(OSError):
            open_dir(root, ("link", "b"))

    def it_refuses_a_root_that_is_a_link(root: Path, tmp_path: Path) -> None:
        (tmp_path / "linked").symlink_to(root)
        with pytest.raises(OSError):
            open_dir(tmp_path / "linked", ())

    def it_closes_what_it_opened_when_it_fails(root: Path) -> None:
        before = len(list(Path("/proc/self/fd").iterdir()))
        with pytest.raises(FileNotFoundError):
            open_dir(root, ("a", "missing"))
        assert len(list(Path("/proc/self/fd").iterdir())) == before
