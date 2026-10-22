import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any


def remove_tree(path: Path) -> None:
    """Remove `path` and everything in it, if it's there.

    Dirs the agent locked against their owner are opened up and tried once more, as
    `TemporaryDirectory` does, but a symlink is never followed. What still won't go raises.
    """
    retried: set[str] = set()

    def reopen(_func: Callable[..., Any], name: str, error: BaseException) -> None:
        if isinstance(error, FileNotFoundError):
            return
        if not isinstance(error, PermissionError) or name in retried:
            raise error
        retried.add(name)
        entry = Path(name)
        for directory in (entry.parent, entry):
            if directory.is_dir() and not directory.is_symlink():
                directory.chmod(0o700)
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry, onexc=reopen)
        else:
            entry.unlink(missing_ok=True)

    shutil.rmtree(path, onexc=reopen)
