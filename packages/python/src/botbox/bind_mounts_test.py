import os
from pathlib import Path

import pytest

from botbox.bind_mounts import bind_mounts

HOME = "/home/user"


@pytest.fixture
def work(tmp_path: Path) -> Path:
    directory = tmp_path / "work"
    directory.mkdir()
    return directory


def describe_bind_mounts() -> None:
    def it_takes_workdir_and_home_by_keyword_only() -> None:
        with pytest.raises(TypeError):
            bind_mounts((), None, HOME)  # type: ignore[call-arg]

    def it_returns_nothing_for_no_mounts() -> None:
        assert bind_mounts((), workdir=None, home=HOME) == []

    def it_returns_each_mount_as_a_volume(work: Path, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        assert bind_mounts(
            [(work, "/work", "rw"), (tmp_path / "tests", Path("/tests"), "ro")],
            workdir=None,
            home=HOME,
        ) == [(str(work), "/work", "rw"), (str(tmp_path / "tests"), "/tests", "ro")]

    def it_resolves_the_host_path(work: Path) -> None:
        assert bind_mounts([(f"{work}/../work", "/w", "ro")], workdir=None, home=HOME) == [
            (str(work), "/w", "ro")
        ]

    def describe_a_missing_host_path() -> None:
        def it_creates_it_as_a_directory_with_its_parents(tmp_path: Path) -> None:
            missing = tmp_path / "a" / "b"
            assert bind_mounts([(missing, "/b", "ro")], workdir=None, home=HOME) == [
                (str(missing), "/b", "ro")
            ]
            assert missing.is_dir()

        def it_owns_it_by_the_calling_user(tmp_path: Path) -> None:
            bind_mounts([(tmp_path / "new", "/new", "rw")], workdir=None, home=HOME)
            assert (tmp_path / "new").stat().st_uid == os.getuid()

        def it_creates_nothing_when_the_workdir_is_outside_every_mount(tmp_path: Path) -> None:
            with pytest.raises(ValueError, match="workdir"):
                bind_mounts([(tmp_path / "new", "/new", "rw")], workdir="/elsewhere", home=HOME)
            assert not (tmp_path / "new").exists()

    def it_leaves_an_existing_host_path_as_it_is(tmp_path: Path) -> None:
        (tmp_path / "file").write_text("kept")
        bind_mounts([(tmp_path / "file", "/file", "ro")], workdir=None, home=HOME)
        assert (tmp_path / "file").read_text() == "kept"

    def describe_workdir() -> None:
        @pytest.mark.parametrize("workdir", ["/work", "/work/", "/work/pkg", Path("/work/a/b")])
        def it_accepts_a_mounted_path_or_one_inside_it(work: Path, workdir: str | Path) -> None:
            bind_mounts([(work, "/work", "rw")], workdir=workdir, home=HOME)

        @pytest.mark.parametrize("workdir", ["/home/user", "/home/user/.claude"])
        def it_accepts_the_home(workdir: str) -> None:
            bind_mounts((), workdir=workdir, home=HOME)

        def it_accepts_anything_under_a_root_mount(work: Path) -> None:
            bind_mounts([(work, "/", "rw")], workdir="/etc", home=HOME)

        def it_accepts_a_mount_written_with_a_trailing_slash(work: Path) -> None:
            bind_mounts([(work, "/work/", "rw")], workdir="/work/pkg", home=HOME)

        @pytest.mark.parametrize("workdir", ["/", "/workspace", "/wor", "/work/../etc", "/home"])
        def it_raises_outside_every_mount(work: Path, workdir: str) -> None:
            with pytest.raises(ValueError, match=rf"workdir {workdir} is not a mounted path"):
                bind_mounts([(work, "/work", "rw")], workdir=workdir, home=HOME)
