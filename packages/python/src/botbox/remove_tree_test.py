from pathlib import Path

import pytest

from botbox.remove_tree import remove_tree


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "home"
    (root / "a" / "b").mkdir(parents=True)
    (root / "a" / "b" / "secret").write_text("token")
    (root / "top").write_text("x")
    return root


def describe_remove_tree() -> None:
    def it_removes_the_dir_and_everything_in_it(tree: Path) -> None:
        remove_tree(tree)
        assert not tree.exists()

    def it_does_nothing_when_it_is_already_gone(tmp_path: Path) -> None:
        remove_tree(tmp_path / "gone")

    def it_opens_up_dirs_locked_against_their_owner(tree: Path) -> None:
        (tree / "a" / "b").chmod(0o500)
        (tree / "a").chmod(0o000)
        remove_tree(tree)
        assert not tree.exists()

    def it_removes_symlinks_without_following_them(tree: Path, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "kept").write_text("x")
        outside.chmod(0o500)
        (tree / "a" / "link").symlink_to(outside)
        (tree / "a").chmod(0o500)
        remove_tree(tree)
        assert not tree.exists()
        assert (outside / "kept").exists()
        assert outside.stat().st_mode & 0o777 == 0o500

    def it_raises_what_it_cannot_fix(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tree / "a").chmod(0o500)

        def refuse(*_args: object, **_kwargs: object) -> None:
            raise PermissionError("not yours")

        monkeypatch.setattr(Path, "chmod", refuse)
        with pytest.raises(PermissionError):
            remove_tree(tree)
        monkeypatch.undo()
        (tree / "a").chmod(0o700)
